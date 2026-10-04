import json
from enum import StrEnum
from pathlib import Path

import pytest

from hemolint.b_core.c_secondary_ports.baseline_store import BaselineStore, FakeBaselineStore
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
from hemolint.c_infrastructure.disk_baseline_store import DiskBaselineStore


class StoreKind(StrEnum):
    fake = "fake"
    disk = "disk"


@pytest.fixture(params=list(StoreKind))
def store(request: pytest.FixtureRequest, tmp_path: Path) -> BaselineStore:
    if StoreKind(request.param) == StoreKind.fake:
        return FakeBaselineStore()
    return DiskBaselineStore(BaselineDirectory(tmp_path / ".hemolint"))


linter = LinterName("fixit")
rule = RuleName("UseFstring")
nested = BaselineFile(source=SourcePath(Path("src/a.py")), linter=linter, rule=rule)
top_level = BaselineFile(source=SourcePath(Path("b.py")), linter=linter, rule=rule)
known = Violation(file=nested, fingerprint=Fingerprint.fake())
other = Violation(file=top_level, fingerprint=Fingerprint.fake())
baseline = Baseline.of((known, known, other))


def test_a_baseline_never_written_reads_as_empty(store: BaselineStore) -> None:
    assert store.read().unwrap() == Baseline.of(())


def test_a_written_baseline_reads_back(store: BaselineStore) -> None:
    _ = store.write(baseline).unwrap()
    assert store.read().unwrap() == baseline


def test_a_second_write_replaces_the_first(store: BaselineStore) -> None:
    remaining = Baseline.of((other,))
    _ = store.write(baseline).unwrap()
    _ = store.write(remaining).unwrap()
    assert store.read().unwrap() == remaining


def test_an_empty_write_empties_the_baseline(store: BaselineStore) -> None:
    _ = store.write(baseline).unwrap()
    _ = store.write(Baseline.of(())).unwrap()
    assert store.read().unwrap() == Baseline.of(())


def test_a_source_file_named_like_a_baseline_file_reads_back(store: BaselineStore) -> None:
    json_source = Baseline.of(
        (
            Violation(
                file=BaselineFile(source=SourcePath(Path("data.json")), linter=linter, rule=rule),
                fingerprint=Fingerprint.fake(),
            ),
        )
    )
    _ = store.write(json_source).unwrap()
    _ = store.write(json_source).unwrap()
    assert store.read().unwrap() == json_source


def test_the_disk_baseline_keeps_one_sorted_file_per_source_file_per_rule(tmp_path: Path) -> None:
    directory = tmp_path / ".hemolint"
    later, earlier = Fingerprint("b = '%s' % y"), Fingerprint("a = '%s' % y")
    _ = (
        DiskBaselineStore(BaselineDirectory(directory))
        .write(
            Baseline.of(
                (
                    Violation(file=nested, fingerprint=later),
                    Violation(file=nested, fingerprint=earlier),
                    Violation(file=nested, fingerprint=earlier),
                )
            )
        )
        .unwrap()
    )
    written = directory / nested.source.root / f"{linter.root}-{rule.root}.json"
    expected = {earlier.root: 2, later.root: 1}
    assert json.loads(written.read_text()) == expected
    assert list(json.loads(written.read_text())) == sorted(expected)


def test_the_disk_baseline_drops_the_directory_of_a_source_file_without_violations(
    tmp_path: Path,
) -> None:
    directory = tmp_path / ".hemolint"
    store = DiskBaselineStore(BaselineDirectory(directory))
    _ = store.write(baseline).unwrap()
    _ = store.write(Baseline.of((other,))).unwrap()
    assert not (directory / nested.source.root.parts[0]).exists()


def test_a_baseline_file_that_is_no_json_is_an_error(tmp_path: Path) -> None:
    directory = tmp_path / ".hemolint"
    (directory / "a.py").mkdir(parents=True)
    _ = (directory / "a.py" / f"{linter.root}-{rule.root}.json").write_text("{")
    assert DiskBaselineStore(BaselineDirectory(directory)).read().is_err()
