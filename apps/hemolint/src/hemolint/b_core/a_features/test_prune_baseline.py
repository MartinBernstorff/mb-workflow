from pathlib import Path

from hemolint.b_core.a_features.prune_baseline import BaselinePruning
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


def test_a_fixed_violation_is_removed_from_the_baseline() -> None:
    store = FakeBaselineStore(Baseline.of((known, known)))
    _ = BaselinePruning.prune(
        LinterOutput(f"{reported_line}\n"),
        LinterFormat.fixit,
        WorkingDirectory.fake(),
        lines,
        store,
    ).unwrap()
    assert store.baseline == Baseline.of((known,))


def test_a_new_violation_is_reported_but_not_added() -> None:
    store = FakeBaselineStore()
    drift = BaselinePruning.prune(
        LinterOutput(f"{reported_line}\n"),
        LinterFormat.fixit,
        WorkingDirectory.fake(),
        lines,
        store,
    ).unwrap()
    assert [violation.reported_as for violation in drift.new] == [LinterLine(reported_line)]
    assert store.baseline == Baseline.of(())


def test_another_linters_violation_is_kept() -> None:
    kept = Baseline.of((other_linters_violation(),))
    store = FakeBaselineStore(kept)
    _ = BaselinePruning.prune(
        LinterOutput(""), LinterFormat.fixit, WorkingDirectory.fake(), lines, store
    ).unwrap()
    assert store.baseline == kept
