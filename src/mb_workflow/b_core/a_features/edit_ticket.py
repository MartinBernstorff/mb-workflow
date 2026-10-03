from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
    from mb_workflow.b_core.d_domain_model.ticket_edit import TicketEdit


def edit_ticket(
    tracker: TicketTracker, issue: IssueIdentifier, edit: TicketEdit, flow_labels: FlowLabels
) -> None:
    checked = edit.checked(flow_labels)
    tracker.update_issue(issue, checked.update(tracker.read_issue_detail(issue), tracker.viewer()))
