from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.issue_tracker import IssueTracker
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
    from mb_workflow.b_core.d_domain_model.ticket_edit import TicketEdit


def edit_ticket(tracker: IssueTracker, issue: IssueIdentifier, edit: TicketEdit) -> None:
    checked = edit.checked()
    tracker.update_issue(issue, checked.update(tracker.read_issue_detail(issue), tracker.viewer()))
