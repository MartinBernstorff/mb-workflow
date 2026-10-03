from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from mb_workflow.b_core.b_domain_services.ticket_report import TicketReport

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
        TicketTracker,
        TicketTrackerError,
    )
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier


def view_ticket(
    tracker: TicketTracker, issue: IssueIdentifier
) -> Result[TicketReport, TicketTrackerError]:
    match tracker.read_issue_detail(issue):
        case Ok(value):
            return Ok(TicketReport.of(value))
        case Err() as failed:
            return failed
