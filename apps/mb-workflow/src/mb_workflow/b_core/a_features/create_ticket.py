from typing import TYPE_CHECKING

from safe_result import Err, Result

from mb_workflow.b_core.b_domain_services.flow_label_check import FlowLabelCheck
from mb_workflow.b_core.d_domain_model.flow import StateNames, WorkflowChart

if TYPE_CHECKING:
    from mb_workflow.b_core.b_domain_services.flow_label_check import MissingFlowLabelsError
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
        TicketTracker,
        TicketTrackerError,
    )
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabelOptionError, FlowLabels
    from mb_workflow.b_core.d_domain_model.issue import CreatedIssue
    from mb_workflow.b_core.d_domain_model.ticket_draft import (
        TicketDefaults,
        TicketDraft,
        TicketDraftError,
    )
    from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses


class TicketCreation:
    @staticmethod
    def create_ticket(
        *,
        tracker: TicketTracker,
        draft: TicketDraft,
        defaults: TicketDefaults,
        flow_labels: FlowLabels,
        statuses: TicketStatuses,
    ) -> Result[
        CreatedIssue,
        TicketDraftError | FlowLabelOptionError | TicketTrackerError | MissingFlowLabelsError,
    ]:
        viewer = tracker.viewer()
        if isinstance(viewer, Err):
            return viewer
        drafted = draft.new_issue(
            defaults=defaults,
            start=StateNames.initial_state(WorkflowChart),
            flow_labels=flow_labels,
            statuses=statuses,
            viewer=viewer.value,
        )
        if isinstance(drafted, Err):
            return drafted
        new = drafted.value
        checked = FlowLabelCheck.require(tracker, flow_labels, new.team)
        if isinstance(checked, Err):
            return checked
        for related in draft.related():
            found = tracker.read_issue(related)
            if isinstance(found, Err):
                return found
        return tracker.create_issue(new)
