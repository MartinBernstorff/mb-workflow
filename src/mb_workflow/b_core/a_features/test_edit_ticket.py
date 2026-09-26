import pytest

from mb_workflow.b_core.a_features.edit_ticket import edit_ticket
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
    FakeTicketTracker,
    TicketTrackerError,
    TrackedIssue,
)
from mb_workflow.b_core.d_domain_model.issue import (
    Assignee,
    IssueIdentifier,
    LabelName,
    LabelNames,
    Projects,
    StatusName,
    StatusNames,
)
from mb_workflow.b_core.d_domain_model.ticket_edit import TicketEdit, TicketEditError


def tracking() -> FakeTicketTracker:
    return FakeTicketTracker(
        LabelNames((LabelName.fake(), LabelName("Backend"))),
        (TrackedIssue.fake(),),
        Projects.fake(),
        StatusNames.fake(),
        Assignee.fake(),
    )


def test_editing_a_ticket_writes_the_title() -> None:
    tracker = tracking()
    edit_ticket(tracker, IssueIdentifier.fake(), TicketEdit.fake())
    assert tracker.read_issue_detail(IssueIdentifier.fake()).title == TicketEdit.fake().title


def test_editing_a_ticket_self_assigns_with_me() -> None:
    tracker = tracking()
    edit = TicketEdit.nothing().model_copy(update={"add_assignee": Assignee.me()})
    edit_ticket(tracker, IssueIdentifier.fake(), edit)
    assert tracker.read_issue_detail(IssueIdentifier.fake()).assignee == Assignee.fake()


def test_editing_a_ticket_swaps_labels() -> None:
    tracker = tracking()
    edit = TicketEdit.nothing().model_copy(
        update={
            "add_labels": LabelNames((LabelName("Backend"),)),
            "remove_labels": LabelNames.fake(),
        }
    )
    edit_ticket(tracker, IssueIdentifier.fake(), edit)
    assert tracker.read_issue(IssueIdentifier.fake()).labels == LabelNames((LabelName("Backend"),))


def test_editing_an_unknown_ticket_fails() -> None:
    with pytest.raises(TicketTrackerError):
        edit_ticket(tracking(), IssueIdentifier("E-404"), TicketEdit.fake())


def test_an_empty_edit_is_refused_before_the_ticket_is_read() -> None:
    with pytest.raises(TicketEditError):
        edit_ticket(tracking(), IssueIdentifier("E-404"), TicketEdit.nothing())


def test_editing_a_ticket_moves_its_status() -> None:
    tracker = tracking()
    edit = TicketEdit.nothing().model_copy(update={"status": StatusName("done")})
    edit_ticket(tracker, IssueIdentifier.fake(), edit)
    assert tracker.read_issue(IssueIdentifier.fake()).status == StatusName("Done")
