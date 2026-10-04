from hemolint.b_core.d_domain_model.baseline import (
    Baseline,
    BaselineChange,
    BaselineFile,
    Count,
    Violation,
)
from hemolint.b_core.d_domain_model.violation import Fingerprint, RuleName


def violation(code: Fingerprint) -> Violation:
    return Violation(file=BaselineFile.fake(), fingerprint=code)


def test_the_order_violations_arrive_in_does_not_change_the_baseline() -> None:
    first, second = violation(Fingerprint("a == None")), violation(Fingerprint("b == None"))
    assert Baseline.of((first, second)) == Baseline.of((second, first))


def test_an_unchanged_baseline_adds_and_removes_nothing() -> None:
    baseline = Baseline.of((violation(Fingerprint("a == None")),))
    assert baseline.change_from(baseline) == BaselineChange(added=Count(0), removed=Count(0))


def test_an_extra_copy_of_a_known_violation_counts_as_added() -> None:
    known = violation(Fingerprint("a == None"))
    change = Baseline.of((known, known)).change_from(Baseline.of((known,)))
    assert change == BaselineChange(added=Count(1), removed=Count(0))


def test_a_fixed_violation_counts_as_removed() -> None:
    fixed = violation(Fingerprint("a == None"))
    change = Baseline.of(()).change_from(Baseline.of((fixed, fixed)))
    assert change == BaselineChange(added=Count(0), removed=Count(2))


def test_the_same_line_under_another_rule_is_another_violation() -> None:
    code = Fingerprint("a == None")
    other_rule = BaselineFile.fake().model_copy(update={"rule": RuleName("Other")})
    before = Baseline.of((Violation(file=BaselineFile.fake(), fingerprint=code),))
    after = Baseline.of((Violation(file=other_rule, fingerprint=code),))
    assert after.change_from(before) == BaselineChange(added=Count(1), removed=Count(1))
