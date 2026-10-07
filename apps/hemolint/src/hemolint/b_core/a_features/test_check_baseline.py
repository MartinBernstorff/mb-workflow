from pathlib import Path

from hemolint.b_core.a_features.check_baseline import BaselineCheck
from hemolint.b_core.c_secondary_ports.baseline_store import FakeBaselineStore
from hemolint.b_core.c_secondary_ports.source_lines import FakeSourceLines
from hemolint.b_core.d_domain_model.baseline import Baseline, BaselineFile, Violation
from hemolint.b_core.d_domain_model.linter_format import LinterFormat
from hemolint.b_core.d_domain_model.linter_output import LinterOutput
from hemolint.b_core.d_domain_model.violation import (
    Fingerprint,
    LinterLine,
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
reported_line = f"{source.root}@1:0 {rule.root}: Use `is`."
lines = FakeSourceLines({source: SourceText(f"{code.root}\n")})


def other_linters_violation() -> Violation:
    return Violation(
        file=BaselineFile(
            source=source, linter=LinterName("pyrefly"), rule=RuleName("bad-assignment")
        ),
        fingerprint=code,
    )


def test_a_violation_missing_from_the_baseline_is_new_under_its_linter_line() -> None:
    drift = BaselineCheck.check(
        LinterOutput(f"{reported_line}\n"),
        LinterFormat.fixit,
        WorkingDirectory.fake(),
        lines,
        FakeBaselineStore(),
    ).unwrap()
    assert [violation.reported_as for violation in drift.new] == [LinterLine(reported_line)]


def test_a_baselined_violation_that_is_no_longer_reported_is_fixed() -> None:
    drift = BaselineCheck.check(
        LinterOutput(""),
        LinterFormat.fixit,
        WorkingDirectory.fake(),
        lines,
        FakeBaselineStore(Baseline.of((known,))),
    ).unwrap()
    assert drift.fixed == Baseline.of((known,))


def test_checking_leaves_the_baseline_as_it_was() -> None:
    previous = Baseline.of((known,))
    store = FakeBaselineStore(previous)
    _ = BaselineCheck.check(
        LinterOutput(f"{reported_line}\n{reported_line}\n"),
        LinterFormat.fixit,
        WorkingDirectory.fake(),
        lines,
        store,
    ).unwrap()
    assert store.baseline == previous


def test_another_linters_baselined_violation_is_not_fixed() -> None:
    drift = BaselineCheck.check(
        LinterOutput(""),
        LinterFormat.fixit,
        WorkingDirectory.fake(),
        lines,
        FakeBaselineStore(Baseline.of((other_linters_violation(),))),
    ).unwrap()
    assert not drift.exists()
