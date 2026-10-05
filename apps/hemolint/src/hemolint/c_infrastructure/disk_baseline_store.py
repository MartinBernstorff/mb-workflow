import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import override

from pydantic import TypeAdapter, ValidationError
from safe_result import Err, Ok, Result

from hemolint.b_core.c_secondary_ports.baseline_store import BaselineStore, BaselineStoreError
from hemolint.b_core.d_domain_model.baseline import (
    Baseline,
    BaselineDirectory,
    BaselineFile,
    Violation,
)
from hemolint.b_core.d_domain_model.violation import (
    Fingerprint,
    LinterName,
    RuleName,
    SourcePath,
)
from hemolint.d_lib.models import Value

_COUNTS = TypeAdapter(dict[str, int])


# One baseline file: each fingerprint with its count, sorted, so merges rarely conflict.
class BaselineFileText(Value[str]):
    @staticmethod
    def fake() -> BaselineFileText:
        return BaselineFileText.of(Counter({Fingerprint.fake(): 1}))

    @staticmethod
    def of(counts: Counter[Fingerprint]) -> BaselineFileText:
        ordered = {
            fingerprint.root: counts[fingerprint]
            for fingerprint in sorted(counts, key=lambda f: f.root)
        }
        return BaselineFileText(json.dumps(ordered, indent=2, ensure_ascii=False) + "\n")

    def decode(self) -> Result[Counter[Fingerprint], ValueError]:
        try:
            counts = _COUNTS.validate_json(self.root)
        except ValidationError as error:
            return Err(error)
        return Ok(Counter({Fingerprint(code): count for code, count in counts.items()}))


# Where one baseline file lives: `<linter>-<rule>/<source path>.json` under the baseline directory.
class BaselineFilePath(Value[Path]):
    @staticmethod
    def fake() -> BaselineFilePath:
        return BaselineFilePath.of(BaselineDirectory.fake(), BaselineFile.fake())

    @staticmethod
    def of(directory: BaselineDirectory, file: BaselineFile) -> BaselineFilePath:
        source = file.source.root
        return BaselineFilePath(
            directory.root
            / f"{file.linter.root}-{file.rule.root}"
            / source.with_name(f"{source.name}.json")
        )

    # Linter names hold no "-", so the first one separates the linter from the rule.
    def decode(self, directory: BaselineDirectory) -> BaselineFile | None:
        rule_directory, *source_parts = self.root.relative_to(directory.root).parts
        linter, separator, rule = rule_directory.partition("-")
        if not separator or not source_parts or self.root.suffix != ".json":
            return None
        return BaselineFile(
            source=SourcePath(Path(*source_parts).with_suffix("")),
            linter=LinterName(linter),
            rule=RuleName(rule),
        )


class DiskBaselineStore(BaselineStore):
    def __init__(self, directory: BaselineDirectory) -> None:
        self._directory = directory

    @override
    def read(self) -> Result[Baseline, BaselineStoreError]:
        violations: list[Violation] = []
        for path in self._baseline_file_paths():
            file = path.decode(self._directory)
            if file is None:
                return Err(
                    BaselineStoreError(f"{path.root} is not at <linter>-<rule>/<source>.json.")
                )
            try:
                counts = BaselineFileText(path.root.read_text()).decode()
            except OSError as error:
                return Err(BaselineStoreError(f"Cannot read {path.root}: {error}"))
            if isinstance(counts, Err):
                return Err(BaselineStoreError(f"{path.root} is no baseline file: {counts.error}"))
            violations.extend(
                Violation(file=file, fingerprint=fingerprint)
                for fingerprint in counts.value.elements()
            )
        return Ok(Baseline.of(violations))

    @override
    def write(self, baseline: Baseline) -> Result[None, BaselineStoreError]:
        root = self._directory.root
        by_file: defaultdict[BaselineFile, Counter[Fingerprint]] = defaultdict(Counter)
        for violation in baseline.root:
            by_file[violation.file][violation.fingerprint] += 1
        wanted = {
            BaselineFilePath.of(self._directory, file): counts for file, counts in by_file.items()
        }
        try:
            for stale in self._baseline_file_paths():
                if stale not in wanted:
                    stale.root.unlink()
            for path, counts in wanted.items():
                path.root.parent.mkdir(parents=True, exist_ok=True)
                _ = path.root.write_text(BaselineFileText.of(counts).root)
            self._remove_empty_directories()
        except OSError as error:
            return Err(BaselineStoreError(f"Cannot write the baseline to {root}: {error}"))
        return Ok(None)

    def _baseline_file_paths(self) -> list[BaselineFilePath]:
        root = self._directory.root
        if not root.exists():
            return []
        return [BaselineFilePath(path) for path in sorted(root.rglob("*.json")) if path.is_file()]

    # Drops the directories that no longer hold violations, deepest first.
    def _remove_empty_directories(self) -> None:
        root = self._directory.root
        if not root.exists():
            return
        directories = sorted(
            (path for path in root.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        )
        for directory in directories:
            if not any(directory.iterdir()):
                directory.rmdir()
