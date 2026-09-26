from typing import TYPE_CHECKING

from mb_workflow.b_core.b_domain_services.ticket_report import TicketReport

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.issue_tracker import IssueTracker
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier


def view_ticket(tracker: IssueTracker, issue: IssueIdentifier) -> TicketReport:
    return TicketReport.of(tracker.view_issue(issue))
