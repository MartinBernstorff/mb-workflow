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
from hemolint.b_core.d_domain_model.linter_output import LinterOutput, UnparsableLineError
from hemolint.b_core.d_domain_model.violation import (
    Fingerprint,
    LineNumber,
    LinterName,
    RuleName,
    SourcePath,
    SourceText,
    WorkingDirectory,
)

source = SourcePath(Path("a.py"))
rule = RuleName("CompareSingletonPrimitivesByIs")
code = Fingerprint("if x == None:")
file = BaselineFile(source=source, linter=LinterName("fixit"), rule=rule)


def output_at(*lines: LineNumber) -> LinterOutput:
    return LinterOutput(
        "".join(f"{source.root}@{line.root}:3 {rule.root}: Use `is`.\n" for line in lines)
    )


def record(
    output: LinterOutput, text: SourceText, store: FakeBaselineStore
) -> BaselineChange | Exception:
    result = BaselineRecording.record(
        output, LinterFormat.fixit, WorkingDirectory.fake(), FakeSourceLines({source: text}), store
    )
    return result.error if isinstance(result, Err) else result.value


def test_each_reported_violation_is_recorded_under_its_source_line() -> None:
    store = FakeBaselineStore()
    _ = record(output_at(LineNumber(2)), SourceText(f"x = 1\n    {code.root}\n"), store)
    assert store.baseline == Baseline.of((Violation(file=file, fingerprint=code),))


def test_recording_reports_what_it_added() -> None:
    change = record(output_at(LineNumber(1)), SourceText(f"{code.root}\n"), FakeBaselineStore())
    assert change == BaselineChange(added=Count(1), removed=Count(0))


def test_a_violation_that_moved_to_another_line_still_matches() -> None:
    store = FakeBaselineStore(Baseline.of((Violation(file=file, fingerprint=code),)))
    change = record(output_at(LineNumber(3)), SourceText(f"\n\n{code.root}\n"), store)
    assert change == BaselineChange(added=Count(0), removed=Count(0))


def test_an_extra_copy_of_a_known_violation_is_recorded_as_new() -> None:
    known = Violation(file=file, fingerprint=code)
    store = FakeBaselineStore(Baseline.of((known,)))
    change = record(
        output_at(LineNumber(1), LineNumber(2)), SourceText(f"{code.root}\n{code.root}\n"), store
    )
    assert change == BaselineChange(added=Count(1), removed=Count(0))
    assert store.baseline == Baseline.of((known, known))


def test_a_fixed_violation_is_removed() -> None:
    store = FakeBaselineStore(Baseline.of((Violation(file=file, fingerprint=code),)))
    change = record(LinterOutput(""), SourceText(""), store)
    assert change == BaselineChange(added=Count(0), removed=Count(1))
    assert store.baseline == Baseline.of(())


def test_unparsable_output_writes_nothing() -> None:
    previous = Baseline.of((Violation(file=file, fingerprint=code),))
    store = FakeBaselineStore(previous)
    output = LinterOutput(f"{output_at().root}b.py: EXCEPTION: Syntax Error @ 1:1.\n")
    assert isinstance(record(output, SourceText(""), store), UnparsableLineError)
    assert store.baseline == previous
