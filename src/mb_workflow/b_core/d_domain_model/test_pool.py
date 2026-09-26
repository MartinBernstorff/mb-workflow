import pytest

from mb_workflow.b_core.d_domain_model.issue import (
    IssueIdentifier,
    IssueStatusName,
    LabelName,
    LabelNames,
)
from mb_workflow.b_core.d_domain_model.pool import Blocker, Blockers, PoolTicket, Ready


def ticket(
    status: IssueStatusName, labels: LabelNames, blockers: Blockers = Blockers(())
) -> PoolTicket:
    return PoolTicket.fake().model_copy(
        update={
            "issue": PoolTicket.fake().issue.model_copy(
                update={"status": status, "labels": labels}
            ),
            "blockers": blockers,
        }
    )


def blocked_by(*statuses: IssueStatusName) -> PoolTicket:
    return ticket(
        IssueStatusName("Specced"),
        LabelNames(()),
        Blockers(
            tuple(
                Blocker(issue=IssueIdentifier(f"MB-{n}"), status=status)
                for n, status in enumerate(statuses, start=100)
            )
        ),
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


@pytest.mark.parametrize("status", ["Merged", "Canceled", "Duplicate", "merged"])
def test_a_resolved_blocker_leaves_a_ticket_ready(status: str) -> None:
    assert blocked_by(IssueStatusName(status)).ready(LabelName("claimed")) == Ready(True)


@pytest.mark.parametrize("status", ["Specced", "Implementing", "QA", "Review", "Merging", "Done"])
def test_an_unresolved_blocker_holds_a_ticket_back(status: str) -> None:
    assert blocked_by(IssueStatusName(status)).ready(LabelName("claimed")) == Ready(False)


def test_one_unresolved_blocker_among_resolved_ones_holds_a_ticket_back() -> None:
    assert blocked_by(
        IssueStatusName("Merged"), IssueStatusName("Review"), IssueStatusName("Canceled")
    ).ready(LabelName("claimed")) == Ready(False)
