import pytest

from mb_workflow.b_core.d_domain_model.issue import IssueStatusName, LabelName, LabelNames
from mb_workflow.b_core.d_domain_model.pool import PoolTicket, Ready


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
