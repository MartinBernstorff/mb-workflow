import pytest

from mb_workflow.b_core.a_features.view_ticket import view_ticket
from mb_workflow.b_core.b_domain_services.ticket_report import TicketReport
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
    FakeTicketTracker,
    TicketTrackerError,
    TrackedIssue,
)
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier, LabelNames


def test_viewing_a_ticket_reports_its_title() -> None:
    tracker = FakeTicketTracker(LabelNames.fake(), (TrackedIssue.fake(),))
    assert view_ticket(tracker, IssueIdentifier.fake()) == TicketReport.fake()


def test_viewing_an_unknown_ticket_fails() -> None:
    tracker = FakeTicketTracker(LabelNames.fake(), ())
    with pytest.raises(TicketTrackerError):
        _ = view_ticket(tracker, IssueIdentifier("E-404"))
