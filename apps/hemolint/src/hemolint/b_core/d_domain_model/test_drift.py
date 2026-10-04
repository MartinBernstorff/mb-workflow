from hemolint.b_core.d_domain_model.baseline import (
    Baseline,
    BaselineFile,
    Count,
    FoundViolation,
    Violation,
)
from hemolint.b_core.d_domain_model.drift import Drift
from hemolint.b_core.d_domain_model.violation import Fingerprint, LinterLine, RuleName

known = Violation(file=BaselineFile.fake(), fingerprint=Fingerprint("a == None"))
other = Violation(file=BaselineFile.fake(), fingerprint=Fingerprint("b == None"))


def found(violation: Violation, reported_as: LinterLine) -> FoundViolation:
    return FoundViolation(violation=violation, reported_as=reported_as)


def test_a_baseline_that_matches_the_violations_has_no_drift() -> None:
    drift = Drift.between(Baseline.of((known,)), (found(known, LinterLine.fake()),))
    assert not drift.exists()


def test_a_violation_missing_from_the_baseline_is_new() -> None:
    reported = found(other, LinterLine("src/app.py@2:0 Rule: b."))
    drift = Drift.between(Baseline.of((known,)), (found(known, LinterLine.fake()), reported))
    assert drift.new == (reported,)


def test_an_extra_copy_of_a_known_violation_is_new_from_its_later_line() -> None:
    first = found(known, LinterLine("src/app.py@1:0 Rule: a."))
    second = found(known, LinterLine("src/app.py@9:0 Rule: a."))
    drift = Drift.between(Baseline.of((known,)), (first, second))
    assert drift.new == (second,)


def test_a_violation_in_the_baseline_but_not_reported_is_fixed() -> None:
    drift = Drift.between(Baseline.of((known, known, other)), (found(other, LinterLine.fake()),))
    assert drift.fixed == Baseline.of((known, known))
    assert drift.exists()


def test_fixed_violations_count_per_baseline_file() -> None:
    other_rule = BaselineFile.fake().model_copy(update={"rule": RuleName("Other")})
    elsewhere = Violation(file=other_rule, fingerprint=known.fingerprint)
    drift = Drift.between(Baseline.of((known, other, elsewhere)), ())
    two, one = Count(2), Count(1)
    assert drift.fixed_per_file() == {BaselineFile.fake(): two, other_rule: one}
