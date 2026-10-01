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
    Filled,
    Limit,
    Occupancy,
    PoolLimits,
    PoolTicket,
    Ready,
    Refusal,
    Slot,
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


def test_a_ticket_without_a_flow_label_is_not_ready() -> None:
    unlabelled = PoolTicket.fake().issue.model_copy(
        update={"labels": LabelNames(()), "grouped": GroupedLabels(())}
    )
    ticket = PoolTicket.fake().model_copy(update={"issue": unlabelled})
    assert ticket.ready(LabelName("claimed"), FlowLabels.fake()) == Ready(False)


def test_a_ticket_carrying_the_claim_label_is_not_ready() -> None:
    claimed = ticket(LabelName("Specced"), LabelName("Claimed"))
    assert claimed.ready(LabelName("claimed"), FlowLabels.fake()) == Ready(False)


def test_other_labels_leave_a_ticket_ready() -> None:
    labelled = ticket(LabelName("Specced"), LabelName("Backend"))
    assert labelled.ready(LabelName("claimed"), FlowLabels.fake()) == Ready(True)


def test_the_defaults_cap_the_total_at_four_and_grilling_at_one() -> None:
    assert PoolLimits() == PoolLimits(total=Limit(4), states={StateName("Grilling"): Limit(1)})


def in_state(state: StateName, *labels: LabelName) -> Slot:
    return Slot(state=state, labels=LabelNames(labels))


def occupied(*slots: Slot) -> Occupancy:
    return Occupancy(slots)


def test_a_state_limit_joins_the_default_grilling_limit() -> None:
    assert PoolLimits.model_validate({"total": 6, "states": {"QA": 2}}).states == {
        StateName("Grilling"): Limit(1),
        StateName("QA"): Limit(2),
    }


def test_a_state_limit_overrides_the_default_whatever_its_case() -> None:
    assert PoolLimits.model_validate({"states": {"grilling": 3}}).states == {
        StateName("Grilling"): Limit(3)
    }


def test_a_state_limit_beside_the_total_points_to_the_states_table() -> None:
    with pytest.raises(ValueError, match=r"QA is no pool limit.*\[pool\.limits\.states\]"):
        _ = PoolLimits.model_validate({"total": 6, "QA": 2})


def test_a_state_outside_the_chart_is_refused() -> None:
    with pytest.raises(ValueError, match="Todo"):
        _ = PoolLimits.model_validate({"states": {"Todo": 1}})


def test_label_limits_default_to_none() -> None:
    assert PoolLimits().labels == {}


def test_the_labels_table_sets_label_limits() -> None:
    assert PoolLimits.model_validate({"labels": {"refactor": 1}}).labels == {
        LabelName("refactor"): Limit(1)
    }


def test_a_negative_limit_is_refused() -> None:
    with pytest.raises(ValueError, match="total"):
        _ = PoolLimits.model_validate({"total": -1})


def test_the_summary_lists_state_and_label_limits() -> None:
    limits = PoolLimits(labels={LabelName("refactor"): Limit(1)})
    assert limits.summary().root == "total 4, Grilling 1, label refactor 1"


def test_a_pool_below_the_total_admits_a_state_without_its_own_limit() -> None:
    refusal = PoolLimits(total=Limit(2)).refusal(
        occupied(in_state(StateName("Specced"))), in_state(StateName("Specced"))
    )
    assert refusal is None


def test_a_pool_at_the_total_admits_nothing() -> None:
    refusal = PoolLimits(total=Limit(2)).refusal(
        occupied(in_state(StateName("Specced")), in_state(StateName("QA"))),
        in_state(StateName("Specced")),
    )
    assert refusal == Refusal("the pool is at its total of 2")


def test_a_full_state_is_not_admitted() -> None:
    refusal = PoolLimits().refusal(
        occupied(in_state(StateName("Grilling"))), in_state(StateName("Grilling"))
    )
    assert refusal == Refusal("Grilling is at its limit of 1")


def test_a_full_state_leaves_other_states_admitted() -> None:
    assert (
        PoolLimits().refusal(
            occupied(in_state(StateName("Grilling"))), in_state(StateName("Specced"))
        )
        is None
    )


def test_a_full_label_is_not_admitted_whatever_the_state() -> None:
    limits = PoolLimits(labels={LabelName("refactor"): Limit(1)})
    refusal = limits.refusal(
        occupied(in_state(StateName("Review"), LabelName("refactor"))),
        in_state(StateName("Specced"), LabelName("refactor")),
    )
    assert refusal == Refusal("label refactor is at its limit of 1")


def test_a_label_limit_matches_whatever_the_case() -> None:
    limits = PoolLimits(labels={LabelName("refactor"): Limit(1)})
    refusal = limits.refusal(
        occupied(in_state(StateName("Review"), LabelName("Refactor"))),
        in_state(StateName("Specced"), LabelName("REFACTOR")),
    )
    assert refusal is not None


def test_a_full_label_leaves_tickets_without_it_admitted() -> None:
    limits = PoolLimits(labels={LabelName("refactor"): Limit(1)})
    assert (
        limits.refusal(
            occupied(in_state(StateName("Review"), LabelName("refactor"))),
            in_state(StateName("Specced")),
        )
        is None
    )


def test_a_label_below_its_limit_is_admitted() -> None:
    limits = PoolLimits(labels={LabelName("refactor"): Limit(2)})
    refusal = limits.refusal(
        occupied(in_state(StateName("Review"), LabelName("refactor"))),
        in_state(StateName("Specced"), LabelName("refactor")),
    )
    assert refusal is None


def test_a_pool_is_filled_once_it_reaches_the_total() -> None:
    occupancy = occupied(in_state(StateName("QA")), in_state(StateName("Review")))
    assert PoolLimits(total=Limit(2)).filled(occupancy) == Filled(True)


def test_a_pool_below_the_total_is_not_filled() -> None:
    assert PoolLimits(total=Limit(2)).filled(occupied(in_state(StateName("QA")))) == Filled(False)


def test_occupancy_holds_each_issue_with_its_flow_state_and_labels() -> None:
    issues = Issues(
        tuple(
            Issue.fake().model_copy(
                update={"grouped": grouped, "labels": LabelNames((LabelName("refactor"),))}
            )
            for grouped in (in_flow(LabelName("QA")), in_flow(LabelName("Merging")), in_flow())
        )
    )
    assert Occupancy.of(issues, FlowLabels.fake()) == occupied(
        in_state(StateName("QA"), LabelName("refactor")),
        in_state(StateName("Merging"), LabelName("refactor")),
    )


def test_an_issue_without_a_flow_label_leaves_the_grilling_limit_open() -> None:
    occupancy = Occupancy.of(
        Issues((Issue.fake().model_copy(update={"grouped": in_flow()}),)), FlowLabels.fake()
    )
    assert PoolLimits().refusal(occupancy, in_state(StateName("Grilling"))) is None


def test_a_started_ticket_joins_the_occupancy() -> None:
    occupancy = occupied(in_state(StateName("QA"))).with_slot(in_state(StateName("Specced")))
    assert occupancy == occupied(in_state(StateName("QA")), in_state(StateName("Specced")))
