from typing import TYPE_CHECKING

import pytest

from mb_workflow.b_core.d_domain_model.issue import (
    Issue,
    Issues,
    IssueStatusName,
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

if TYPE_CHECKING:
    from pydantic import JsonValue


def ticket(status: IssueStatusName, labels: LabelNames) -> PoolTicket:
    return PoolTicket.fake().model_copy(
        update={
            "issue": PoolTicket.fake().issue.model_copy(update={"status": status, "labels": labels})
        }
    )


@pytest.mark.parametrize("status", ["Grilling", "Specced", "Implementing", "Merging", "specced"])
def test_an_unclaimed_ticket_in_a_workable_state_is_ready(status: str) -> None:
    assert ticket(IssueStatusName(status), LabelNames(())).ready(LabelName("claimed")) == Ready(
        True
    )


@pytest.mark.parametrize(
    "status", ["Backlog", "Speccing", "QA", "Review", "Merged", "Canceled", "Todo"]
)
def test_a_ticket_in_any_other_state_is_not_ready(status: str) -> None:
    assert ticket(IssueStatusName(status), LabelNames(())).ready(LabelName("claimed")) == Ready(
        False
    )


def test_a_ticket_carrying_the_claim_label_is_not_ready() -> None:
    claimed = ticket(IssueStatusName("Specced"), LabelNames((LabelName("Claimed"),)))
    assert claimed.ready(LabelName("claimed")) == Ready(False)


def test_other_labels_leave_a_ticket_ready() -> None:
    labelled = ticket(IssueStatusName("Specced"), LabelNames((LabelName("Backend"),)))
    assert labelled.ready(LabelName("claimed")) == Ready(True)


def occupied(*statuses: IssueStatusName) -> Occupancy:
    return Occupancy(statuses)


def limits(table: JsonValue) -> PoolLimits:
    return PoolLimits.model_validate(table)


def test_the_defaults_cap_the_total_at_four_and_grilling_at_one() -> None:
    assert PoolLimits() == PoolLimits(
        total=Limit(4), statuses={IssueStatusName("Grilling"): Limit(1)}
    )


def test_a_status_limit_joins_the_default_grilling_limit() -> None:
    assert limits({"total": 6, "QA": 2}).statuses == {
        IssueStatusName("Grilling"): Limit(1),
        IssueStatusName("QA"): Limit(2),
    }


def test_a_status_limit_overrides_the_default_whatever_its_case() -> None:
    assert limits({"grilling": 3}).statuses == {IssueStatusName("Grilling"): Limit(3)}


def test_a_status_outside_the_chart_is_refused() -> None:
    with pytest.raises(ValueError, match="Todo"):
        _ = limits({"Todo": 1})


def test_a_negative_limit_is_refused() -> None:
    with pytest.raises(ValueError, match="total"):
        _ = limits({"total": -1})


def test_a_pool_below_the_total_admits_a_status_without_its_own_limit() -> None:
    assert limits({"total": 2}).admits(
        occupied(IssueStatusName("Specced")), IssueStatusName("Specced")
    ) == Admitted(True)


def test_a_pool_at_the_total_admits_nothing() -> None:
    assert limits({"total": 2}).admits(
        occupied(IssueStatusName("Specced"), IssueStatusName("QA")), IssueStatusName("Specced")
    ) == Admitted(False)


def test_a_full_status_is_not_admitted() -> None:
    assert limits({}).admits(
        occupied(IssueStatusName("grilling")), IssueStatusName("Grilling")
    ) == Admitted(False)


def test_a_full_status_leaves_other_statuses_admitted() -> None:
    assert limits({}).admits(
        occupied(IssueStatusName("Grilling")), IssueStatusName("Specced")
    ) == Admitted(True)


def test_a_pool_is_filled_once_it_reaches_the_total() -> None:
    assert limits({"total": 2}).filled(
        occupied(IssueStatusName("QA"), IssueStatusName("Review"))
    ) == Filled(True)


def test_a_pool_below_the_total_is_not_filled() -> None:
    assert limits({"total": 2}).filled(occupied(IssueStatusName("QA"))) == Filled(False)


def test_occupancy_counts_each_issue_under_its_status() -> None:
    issues = Issues(
        tuple(
            Issue.fake().model_copy(update={"status": IssueStatusName(s)})
            for s in ("QA", "Merging")
        )
    )
    assert Occupancy.of(issues) == occupied(IssueStatusName("QA"), IssueStatusName("Merging"))


def test_a_started_ticket_joins_the_occupancy() -> None:
    assert occupied(IssueStatusName("QA")).plus(IssueStatusName("Specced")) == occupied(
        IssueStatusName("QA"), IssueStatusName("Specced")
    )
