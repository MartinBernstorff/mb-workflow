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


def file_of(source: SourcePath) -> BaselineFile:
    return BaselineFile(source=source, linter=LinterName("fixit"), rule=RuleName("UseFstring"))


def baseline() -> Baseline:
    known = Violation(
        file=file_of(SourcePath(Path("src/a.py"))), fingerprint=Fingerprint("x = '%s' % y")
    )
    other = Violation(
        file=file_of(SourcePath(Path("b.py"))), fingerprint=Fingerprint("z = '%s' % y")
    )
    return Baseline.of((known, known, other))


def test_a_baseline_never_written_reads_as_empty(store: BaselineStore) -> None:
    assert store.read().unwrap() == Baseline.of(())


def test_a_written_baseline_reads_back(store: BaselineStore) -> None:
    _ = store.write(baseline()).unwrap()
    assert store.read().unwrap() == baseline()


def test_a_second_write_replaces_the_first(store: BaselineStore) -> None:
    remaining = Baseline.of(baseline().root[:1])
    _ = store.write(baseline()).unwrap()
    _ = store.write(remaining).unwrap()
    assert store.read().unwrap() == remaining


def test_an_empty_write_empties_the_baseline(store: BaselineStore) -> None:
    _ = store.write(baseline()).unwrap()
    _ = store.write(Baseline.of(())).unwrap()
    assert store.read().unwrap() == Baseline.of(())


def test_the_disk_baseline_keeps_one_sorted_file_per_source_file_per_rule(tmp_path: Path) -> None:
    directory = tmp_path / ".hemolint"
    first, second = Fingerprint("b = '%s' % y"), Fingerprint("a = '%s' % y")
    file = file_of(SourcePath(Path("src/a.py")))
    _ = (
        DiskBaselineStore(BaselineDirectory(directory))
        .write(
            Baseline.of(
                (
                    Violation(file=file, fingerprint=first),
                    Violation(file=file, fingerprint=second),
                    Violation(file=file, fingerprint=second),
                )
            )
        )
        .unwrap()
    )
    written = directory / "src/a.py" / "fixit-UseFstring.json"
    expected = {second.root: 2, first.root: 1}
    assert json.loads(written.read_text()) == expected
    assert list(json.loads(written.read_text())) == sorted(expected)


def test_the_disk_baseline_drops_the_directory_of_a_source_file_without_violations(
    tmp_path: Path,
) -> None:
    directory = tmp_path / ".hemolint"
    store = DiskBaselineStore(BaselineDirectory(directory))
    kept = Violation(
        file=file_of(SourcePath(Path("b.py"))), fingerprint=Fingerprint("z = '%s' % y")
    )
    _ = store.write(baseline()).unwrap()
    _ = store.write(Baseline.of((kept,))).unwrap()
    assert not (directory / "src").exists()


def test_a_baseline_file_that_is_no_json_is_an_error(tmp_path: Path) -> None:
    directory = tmp_path / ".hemolint"
    (directory / "a.py").mkdir(parents=True)
    _ = (directory / "a.py" / "fixit-UseFstring.json").write_text("{")
    assert DiskBaselineStore(BaselineDirectory(directory)).read().is_err()
