import json
from collections import Counter, defaultdict
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


class DiskBaselineStore(BaselineStore):
    def __init__(self, directory: BaselineDirectory) -> None:
        self._directory = directory

    @override
    def read(self) -> Result[Baseline, BaselineStoreError]:
        root = self._directory.root
        violations: list[Violation] = []
        for path in sorted(root.rglob("*.json")):
            linter, separator, rule = path.stem.partition("-")
            if not separator:
                return Err(BaselineStoreError(f"{path} is not named <linter>-<rule>.json."))
            file = BaselineFile(
                source=SourcePath(path.parent.relative_to(root)),
                linter=LinterName(linter),
                rule=RuleName(rule),
            )
            try:
                counts = BaselineFileText(path.read_text()).decode()
            except OSError as error:
                return Err(BaselineStoreError(f"Cannot read {path}: {error}"))
            if isinstance(counts, Err):
                return Err(BaselineStoreError(f"{path} is no baseline file: {counts.error}"))
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
            root / file.source.root / f"{file.linter.root}-{file.rule.root}.json": counts
            for file, counts in by_file.items()
        }
        try:
            if root.exists():
                for stale in root.rglob("*.json"):
                    if stale not in wanted:
                        stale.unlink()
            for path, counts in wanted.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                _ = path.write_text(BaselineFileText.of(counts).root)
            self._remove_empty_directories()
        except OSError as error:
            return Err(BaselineStoreError(f"Cannot write the baseline to {root}: {error}"))
        return Ok(None)

    # Drops the directories of source files that no longer hold violations, deepest first.
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
