from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from mb_workflow.b_core.b_domain_services.flow_label_check import FlowLabelCheck

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.d_domain_model.flow import UnknownStateError
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabelOptionError, FlowLabels
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
    from mb_workflow.b_core.d_domain_model.ticket_edit import TicketEdit, TicketEditError
    from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses


class TicketEditor:
    @staticmethod
    def apply_edit(
        tracker: TicketTracker,
        issue: IssueIdentifier,
        edit: TicketEdit,
        flow_labels: FlowLabels,
        statuses: TicketStatuses,
    ) -> Result[None, TicketEditError | FlowLabelOptionError | UnknownStateError]:
        match edit.checked(flow_labels):
            case Ok(checked):
                if checked.state is not None:
                    FlowLabelCheck.require(tracker, flow_labels, tracker.team_of(issue))
                # Linear relates the issues after updating the fields, so an unknown one must be caught beforehand.
                for related in checked.related():
                    _ = tracker.read_issue(related)
                current = tracker.read_issue_detail(issue)
                tracker.update_issue(
                    issue, checked.update(current, tracker.viewer(), flow_labels, statuses)
                )
                return Ok(None)
            case Err() as failed:
                return failed
