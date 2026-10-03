from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from mb_workflow.b_core.b_domain_services.flow_label_check import FlowLabelCheck

if TYPE_CHECKING:
    from mb_workflow.b_core.b_domain_services.flow_label_check import MissingFlowLabelsError
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
        TicketTracker,
        TicketTrackerError,
    )
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
    ) -> Result[
        None,
        TicketEditError
        | FlowLabelOptionError
        | UnknownStateError
        | TicketTrackerError
        | MissingFlowLabelsError,
    ]:
        checked = edit.checked(flow_labels, issue)
        if isinstance(checked, Err):
            return checked
        if checked.value.state is not None:
            labelled = FlowLabelCheck.require_for_issue(tracker, flow_labels, issue)
            if isinstance(labelled, Err):
                return labelled
        for related in checked.value.related_issues():
            found = tracker.read_issue(related)
            if isinstance(found, Err):
                return found
        current = tracker.read_issue_detail(issue)
        if isinstance(current, Err):
            return current
        viewer = tracker.viewer()
        if isinstance(viewer, Err):
            return viewer
        tracker.update_issue(
            issue, checked.value.update(current.value, viewer.value, flow_labels, statuses)
        )
        return Ok(None)
