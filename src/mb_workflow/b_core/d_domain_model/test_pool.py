import pytest

from mb_workflow.b_core.d_domain_model.flow import StateName
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
from mb_workflow.b_core.d_domain_model.issue import (
    GroupedLabel,
    GroupedLabels,
    Issue,
    Issues,
    LabelGroupName,
    LabelName,
    LabelNames,
)
from mb_workflow.b_core.d_domain_model.pool import (
    Admitted,
    Filled,
    Limit,
    Occupancy,
    PoolLimits,
    PoolTicket,
    Ready,
)


def in_flow(*labels: LabelName) -> GroupedLabels:
    return GroupedLabels(
        tuple(GroupedLabel(group=LabelGroupName.fake(), label=label) for label in labels)
    )


def ticket(flow: LabelName, *others: LabelName) -> PoolTicket:
    issue = PoolTicket.fake().issue.model_copy(
        update={"labels": LabelNames((flow, *others)), "grouped": in_flow(flow)}
    )
    return PoolTicket.fake().model_copy(update={"issue": issue})


@pytest.mark.parametrize(
    "state", ["Grilling", "Speccing", "Specced", "Implementing", "Merging", "specced"]
)
def test_an_unclaimed_ticket_in_a_workable_state_is_ready(state: str) -> None:
    assert ticket(LabelName(state)).ready(LabelName("claimed"), FlowLabels.fake()) == Ready(True)


@pytest.mark.parametrize("state", ["QA", "Review", "Merged"])
def test_a_ticket_in_any_other_state_is_not_ready(state: str) -> None:
    assert ticket(LabelName(state)).ready(LabelName("claimed"), FlowLabels.fake()) == Ready(False)


def test_a_ticket_carrying_the_claim_label_is_not_ready() -> None:
    claimed = ticket(LabelName("Specced"), LabelName("Claimed"))
    assert claimed.ready(LabelName("claimed"), FlowLabels.fake()) == Ready(False)


def test_other_labels_leave_a_ticket_ready() -> None:
    labelled = ticket(LabelName("Specced"), LabelName("Backend"))
    assert labelled.ready(LabelName("claimed"), FlowLabels.fake()) == Ready(True)


def test_the_defaults_cap_the_total_at_four_and_grilling_at_one() -> None:
    assert PoolLimits() == PoolLimits(total=Limit(4), states={StateName("Grilling"): Limit(1)})


def test_a_state_limit_joins_the_default_grilling_limit() -> None:
    assert PoolLimits.model_validate({"total": 6, "QA": 2}).states == {
        StateName("Grilling"): Limit(1),
        StateName("QA"): Limit(2),
    }


def test_a_state_limit_overrides_the_default_whatever_its_case() -> None:
    assert PoolLimits.model_validate({"grilling": 3}).states == {StateName("Grilling"): Limit(3)}


def test_a_state_outside_the_chart_is_refused() -> None:
    with pytest.raises(ValueError, match="Todo"):
        _ = PoolLimits.model_validate({"Todo": 1})


def test_a_state_outside_the_chart_is_refused_under_the_states_key() -> None:
    with pytest.raises(ValueError, match="Todo"):
        _ = PoolLimits.model_validate({"states": {"Todo": 1}})


def test_a_negative_limit_is_refused() -> None:
    with pytest.raises(ValueError, match="total"):
        _ = PoolLimits.model_validate({"total": -1})


def test_a_pool_below_the_total_admits_a_state_without_its_own_limit() -> None:
    occupancy = Occupancy((StateName("Specced"),))
    admitted = PoolLimits(total=Limit(2)).admits(occupancy, StateName("Specced"))
    assert admitted == Admitted(True)


def test_a_pool_at_the_total_admits_nothing() -> None:
    occupancy = Occupancy((StateName("Specced"), StateName("QA")))
    admitted = PoolLimits(total=Limit(2)).admits(occupancy, StateName("Specced"))
    assert admitted == Admitted(False)


def test_a_full_state_is_not_admitted() -> None:
    occupancy = Occupancy((StateName("Grilling"),))
    assert PoolLimits().admits(occupancy, StateName("Grilling")) == Admitted(False)


def test_a_full_state_leaves_other_states_admitted() -> None:
    occupancy = Occupancy((StateName("Grilling"),))
    assert PoolLimits().admits(occupancy, StateName("Specced")) == Admitted(True)


def test_a_pool_is_filled_once_it_reaches_the_total() -> None:
    occupancy = Occupancy((StateName("QA"), StateName("Review")))
    assert PoolLimits(total=Limit(2)).filled(occupancy) == Filled(True)


def test_a_pool_below_the_total_is_not_filled() -> None:
    occupancy = Occupancy((StateName("QA"),))
    assert PoolLimits(total=Limit(2)).filled(occupancy) == Filled(False)


def test_occupancy_counts_each_issue_under_its_flow_state() -> None:
    issues = Issues(
        tuple(
            Issue.fake().model_copy(update={"grouped": grouped})
            for grouped in (in_flow(LabelName("QA")), in_flow(LabelName("Merging")), in_flow())
        )
    )
    assert Occupancy.of(issues, FlowLabels.fake()) == Occupancy(
        (StateName("QA"), StateName("Merging"), StateName("Grilling"))
    )


def test_a_started_ticket_joins_the_occupancy() -> None:
    occupancy = Occupancy((StateName("QA"),)).with_ticket_in(StateName("Specced"))
    assert occupancy == Occupancy((StateName("QA"), StateName("Specced")))
