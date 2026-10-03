from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabelOptionError, FlowLabels
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
    from mb_workflow.b_core.d_domain_model.ticket_edit import TicketEdit, TicketEditError


class TicketEditor:
    @staticmethod
    def apply_edit(
        tracker: TicketTracker, issue: IssueIdentifier, edit: TicketEdit, flow_labels: FlowLabels
    ) -> Result[None, TicketEditError | FlowLabelOptionError]:
        match edit.checked(flow_labels):
            case Ok(checked):
                current = tracker.read_issue_detail(issue)
                tracker.update_issue(issue, checked.update(current, tracker.viewer()))
                return Ok(None)
            case Err() as failed:
                return failed
