import pytest
from assertions import Assert
from safe_result import Ok

from mb_workflow.b_core.d_domain_model.flow import FlowError, StateName
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


@pytest.mark.parametrize("state", ["grill", "to-ticket", "todo", "implementing", "merging", "TODO"])
def test_an_unclaimed_ticket_in_a_workable_state_is_ready(state: str) -> None:
    Assert.that(ticket(LabelName(state)).ready(LabelName("claimed"), FlowLabels.fake())).matches(
        Ready(True)
    )


@pytest.mark.parametrize("state", ["qa", "review", "merged"])
def test_a_ticket_in_any_other_state_is_not_ready(state: str) -> None:
    Assert.that(ticket(LabelName(state)).ready(LabelName("claimed"), FlowLabels.fake())).matches(
        Ready(False)
    )


def test_a_ticket_without_a_flow_label_is_not_ready() -> None:
    unlabelled = PoolTicket.fake().issue.model_copy(
        update={"labels": LabelNames(()), "grouped": GroupedLabels(())}
    )
    ticket = PoolTicket.fake().model_copy(update={"issue": unlabelled})
    Assert.that(ticket.ready(LabelName("claimed"), FlowLabels.fake())).matches(Ready(False))


def test_a_ticket_carrying_the_claim_label_is_not_ready() -> None:
    claimed = ticket(LabelName("todo"), LabelName("Claimed"))
    Assert.that(claimed.ready(LabelName("claimed"), FlowLabels.fake())).matches(Ready(False))


def test_other_labels_leave_a_ticket_ready() -> None:
    labelled = ticket(LabelName("todo"), LabelName("Backend"))
    Assert.that(labelled.ready(LabelName("claimed"), FlowLabels.fake())).matches(Ready(True))


def test_the_defaults_cap_the_total_at_four_and_grill_at_one() -> None:
    Assert.that(PoolLimits()).matches(
        PoolLimits(total=Limit(4), states={StateName("grill"): Limit(1)})
    )


def in_state(state: StateName, *labels: LabelName) -> Slot:
    return Slot(state=state, labels=LabelNames(labels))


def occupied(*slots: Slot) -> Occupancy:
    return Occupancy(slots)


def test_a_state_limit_joins_the_default_grill_limit() -> None:
    Assert.that(PoolLimits.model_validate({"total": 6, "states": {"QA": 2}}).states).matches(
        {
            StateName("grill"): Limit(1),
            StateName("qa"): Limit(2),
        }
    )


def test_a_state_limit_overrides_the_default_whatever_its_case() -> None:
    Assert.that(PoolLimits.model_validate({"states": {"GRILL": 3}}).states).matches(
        {StateName("grill"): Limit(3)}
    )


def test_a_state_limit_beside_the_total_points_to_the_states_table() -> None:
    with pytest.raises(ValueError, match=r"QA is no pool limit.*\[pool\.limits\.states\]"):
        _ = PoolLimits.model_validate({"total": 6, "QA": 2})


def test_a_state_outside_the_chart_is_refused_listing_the_chart_states() -> None:
    with pytest.raises(
        ValueError, match=r"No flow state is named Specced\. Use one of grill, to-ticket,"
    ):
        _ = PoolLimits.model_validate({"states": {"Specced": 1}})


def test_a_state_limited_twice_in_different_casings_is_refused() -> None:
    chart, capitalised = "todo", "Todo"
    with pytest.raises(ValueError, match=f"{chart}, {capitalised}"):
        _ = PoolLimits.model_validate({"states": {chart: 1, capitalised: 2}})


def test_label_limits_default_to_none() -> None:
    Assert.that(PoolLimits().labels).matches({})


def test_the_labels_table_sets_label_limits() -> None:
    Assert.that(PoolLimits.model_validate({"labels": {"refactor": 1}}).labels).matches(
        {LabelName("refactor"): Limit(1)}
    )


def test_a_negative_limit_is_refused() -> None:
    with pytest.raises(ValueError, match="total"):
        _ = PoolLimits.model_validate({"total": -1})


def test_the_summary_lists_state_and_label_limits() -> None:
    limits = PoolLimits(labels={LabelName("refactor"): Limit(1)})
    Assert.that(limits.summary().root).matches("total 4, grill 1, label refactor 1")


def test_a_pool_below_the_total_admits_a_state_without_its_own_limit() -> None:
    refusal = PoolLimits(total=Limit(2)).refusal(
        occupied(in_state(StateName("todo"))), in_state(StateName("todo"))
    )
    Assert.that(refusal).matches(None)


def test_a_pool_at_the_total_admits_nothing() -> None:
    refusal = PoolLimits(total=Limit(2)).refusal(
        occupied(in_state(StateName("todo")), in_state(StateName("qa"))),
        in_state(StateName("todo")),
    )
    Assert.that(refusal).matches(Refusal("the pool is at its total of 2"))


def test_a_full_state_is_not_admitted() -> None:
    refusal = PoolLimits().refusal(
        occupied(in_state(StateName("grill"))), in_state(StateName("grill"))
    )
    Assert.that(refusal).matches(Refusal("grill is at its limit of 1"))


def test_a_full_state_leaves_other_states_admitted() -> None:
    Assert.that(
        PoolLimits().refusal(occupied(in_state(StateName("grill"))), in_state(StateName("todo")))
    ).matches(None)


def test_a_full_label_is_not_admitted_whatever_the_state() -> None:
    limits = PoolLimits(labels={LabelName("refactor"): Limit(1)})
    refusal = limits.refusal(
        occupied(in_state(StateName("review"), LabelName("refactor"))),
        in_state(StateName("todo"), LabelName("refactor")),
    )
    Assert.that(refusal).matches(Refusal("label refactor is at its limit of 1"))


def test_a_label_limit_matches_whatever_the_case() -> None:
    limits = PoolLimits(labels={LabelName("refactor"): Limit(1)})
    refusal = limits.refusal(
        occupied(in_state(StateName("review"), LabelName("Refactor"))),
        in_state(StateName("todo"), LabelName("REFACTOR")),
    )
    _ = Assert.that(refusal).exists()


def test_a_full_label_leaves_tickets_without_it_admitted() -> None:
    limits = PoolLimits(labels={LabelName("refactor"): Limit(1)})
    Assert.that(
        limits.refusal(
            occupied(in_state(StateName("review"), LabelName("refactor"))),
            in_state(StateName("todo")),
        )
    ).matches(None)


def test_a_label_below_its_limit_is_admitted() -> None:
    limits = PoolLimits(labels={LabelName("refactor"): Limit(2)})
    refusal = limits.refusal(
        occupied(in_state(StateName("review"), LabelName("refactor"))),
        in_state(StateName("todo"), LabelName("refactor")),
    )
    Assert.that(refusal).matches(None)


def test_a_pool_is_filled_once_it_reaches_the_total() -> None:
    occupancy = occupied(in_state(StateName("qa")), in_state(StateName("review")))
    Assert.that(PoolLimits(total=Limit(2)).filled(occupancy)).matches(Filled(True))


def test_a_pool_below_the_total_is_not_filled() -> None:
    Assert.that(PoolLimits(total=Limit(2)).filled(occupied(in_state(StateName("qa"))))).matches(
        Filled(False)
    )


def test_occupancy_holds_each_issue_with_its_flow_state_and_labels() -> None:
    issues = Issues(
        tuple(
            Issue.fake().model_copy(
                update={"grouped": grouped, "labels": LabelNames((LabelName("refactor"),))}
            )
            for grouped in (in_flow(LabelName("qa")), in_flow(LabelName("merging")), in_flow())
        )
    )
    Assert.that(Occupancy.of(issues, FlowLabels.fake())).matches(
        Ok(
            occupied(
                in_state(StateName("qa"), LabelName("refactor")),
                in_state(StateName("merging"), LabelName("refactor")),
            )
        )
    )


def test_an_issue_with_two_flow_labels_leaves_the_occupancy_unknown() -> None:
    issues = Issues(
        (
            Issue.fake().model_copy(
                update={"grouped": in_flow(LabelName("qa"), LabelName("review"))}
            ),
        )
    )
    counted = Occupancy.of(issues, FlowLabels.fake())
    _ = Assert.that(counted.error).is_instance(FlowError)


def test_an_issue_without_a_flow_label_leaves_the_grill_limit_open() -> None:
    occupancy = Occupancy.of(
        Issues((Issue.fake().model_copy(update={"grouped": in_flow()}),)), FlowLabels.fake()
    ).unwrap()
    Assert.that(PoolLimits().refusal(occupancy, in_state(StateName("grill")))).matches(None)


def test_a_started_ticket_joins_the_occupancy() -> None:
    occupancy = occupied(in_state(StateName("qa"))).with_slot(in_state(StateName("todo")))
    Assert.that(occupancy).matches(occupied(in_state(StateName("qa")), in_state(StateName("todo"))))
