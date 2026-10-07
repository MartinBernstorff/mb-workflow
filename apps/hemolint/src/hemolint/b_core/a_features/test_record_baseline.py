import json
from pathlib import Path

from safe_result import Err

from hemolint.b_core.a_features.record_baseline import BaselineRecording
from hemolint.b_core.c_secondary_ports.baseline_store import FakeBaselineStore
from hemolint.b_core.c_secondary_ports.source_lines import FakeSourceLines
from hemolint.b_core.d_domain_model.baseline import (
    Baseline,
    BaselineChange,
    BaselineFile,
    Count,
    Violation,
)
from hemolint.b_core.d_domain_model.linter_format import LinterFormat
from hemolint.b_core.d_domain_model.linter_output import LinterOutput, UnparsableOutputError
from hemolint.b_core.d_domain_model.violation import (
    Fingerprint,
    LinterName,
    RuleName,
    SourcePath,
    SourceText,
    WorkingDirectory,
)

source = SourcePath(Path("a.py"))
rule = RuleName("CompareSingletonPrimitivesByIs")
code = Fingerprint("if x == None:")
known = Violation(
    file=BaselineFile(source=source, linter=LinterName("fixit"), rule=rule), fingerprint=code
)
on_line_1 = LinterOutput(f"{source.root}@1:0 {rule.root}: Use `is`.\n")
on_line_2 = LinterOutput(f"{source.root}@2:0 {rule.root}: Use `is`.\n")


class SourceFile:
    @staticmethod
    def lines_holding(text: SourceText) -> FakeSourceLines:
        return FakeSourceLines({source: text})


def test_each_reported_violation_is_recorded_under_its_source_line() -> None:
    store = FakeBaselineStore()
    _ = BaselineRecording.record(
        on_line_2,
        LinterFormat.fixit,
        WorkingDirectory.fake(),
        SourceFile.lines_holding(SourceText(f"x = 1\n    {code.root}\n")),
        store,
    ).unwrap()
    assert store.baseline == Baseline.of((known,))


def test_recording_reports_what_it_added() -> None:
    change = BaselineRecording.record(
        on_line_1,
        LinterFormat.fixit,
        WorkingDirectory.fake(),
        SourceFile.lines_holding(SourceText(f"{code.root}\n")),
        FakeBaselineStore(),
    ).unwrap()
    one_added = BaselineChange(added=Count(1), removed=Count(0))
    assert change == one_added


def test_a_violation_that_moved_to_another_line_still_matches() -> None:
    store = FakeBaselineStore(Baseline.of((known,)))
    _ = BaselineRecording.record(
        on_line_2,
        LinterFormat.fixit,
        WorkingDirectory.fake(),
        SourceFile.lines_holding(SourceText(f"\n{code.root}\n")),
        store,
    ).unwrap()
    assert store.baseline == Baseline.of((known,))


def test_an_extra_copy_of_a_known_violation_is_recorded_as_new() -> None:
    store = FakeBaselineStore(Baseline.of((known,)))
    _ = BaselineRecording.record(
        LinterOutput(on_line_1.root + on_line_2.root),
        LinterFormat.fixit,
        WorkingDirectory.fake(),
        SourceFile.lines_holding(SourceText(f"{code.root}\n{code.root}\n")),
        store,
    ).unwrap()
    assert store.baseline == Baseline.of((known, known))


def test_a_fixed_violation_is_removed() -> None:
    store = FakeBaselineStore(Baseline.of((known,)))
    _ = BaselineRecording.record(
        LinterOutput(""),
        LinterFormat.fixit,
        WorkingDirectory.fake(),
        SourceFile.lines_holding(SourceText("")),
        store,
    ).unwrap()
    assert store.baseline == Baseline.of(())


def test_unparsable_output_writes_nothing() -> None:
    previous = Baseline.of((known,))
    store = FakeBaselineStore(previous)
    result = BaselineRecording.record(
        LinterOutput(f"{on_line_1.root}b.py: EXCEPTION: Syntax Error @ 1:1.\n"),
        LinterFormat.fixit,
        WorkingDirectory.fake(),
        SourceFile.lines_holding(SourceText(f"{code.root}\n")),
        store,
    )
    assert isinstance(result, Err)
    assert isinstance(result.error, UnparsableOutputError)
    assert store.baseline == previous


def test_a_global_violation_is_recorded_under_the_global_source_without_reading_lines() -> None:
    kind = RuleName("UnusedDependencies")
    payload = {"dependency": "b"}
    store = FakeBaselineStore()
    _ = BaselineRecording.record(
        LinterOutput(
            json.dumps(
                [{"Global": {"severity": "Error", "details": {"Code": {kind.root: payload}}}}]
            )
        ),
        LinterFormat.tach,
        WorkingDirectory.fake(),
        FakeSourceLines({}),
        store,
    ).unwrap()
    recorded = Violation(
        file=BaselineFile(
            source=SourcePath.global_diagnostics(), linter=LinterName("tach"), rule=kind
        ),
        fingerprint=Fingerprint('{"dependency":"b"}'),
    )
    assert store.baseline == Baseline.of((recorded,))


def test_another_linters_violation_is_kept() -> None:
    pyrefly = Violation(
        file=BaselineFile(
            source=source, linter=LinterName("pyrefly"), rule=RuleName("bad-assignment")
        ),
        fingerprint=code,
    )
    store = FakeBaselineStore(Baseline.of((pyrefly,)))
    _ = BaselineRecording.record(
        on_line_1,
        LinterFormat.fixit,
        WorkingDirectory.fake(),
        SourceFile.lines_holding(SourceText(f"{code.root}\n")),
        store,
    ).unwrap()
    assert store.baseline == Baseline.of((pyrefly, known))
