from typing import TYPE_CHECKING

from mb_workflow.b_core.b_domain_services.ticket_report import TicketReport

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier


def view_ticket(tracker: TicketTracker, issue: IssueIdentifier) -> TicketReport:
    return TicketReport.of(tracker.read_issue_detail(issue))
