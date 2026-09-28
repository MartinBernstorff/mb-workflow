from typing import TYPE_CHECKING

from mb_workflow.b_core.b_domain_services.flow_label_check import require_flow_labels
from mb_workflow.b_core.d_domain_model.flow import StateNames, WorkflowChart

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.issue import CreatedIssue
    from mb_workflow.b_core.d_domain_model.ticket_draft import TicketDefaults, TicketDraft
    from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses


def create_ticket(
    *,
    tracker: TicketTracker,
    draft: TicketDraft,
    defaults: TicketDefaults,
    flow_labels: FlowLabels,
    statuses: TicketStatuses,
) -> CreatedIssue:
    require_flow_labels(tracker, flow_labels)
    new = draft.new_issue(
        defaults=defaults,
        start=StateNames.initial_state(WorkflowChart),
        flow_labels=flow_labels,
        statuses=statuses,
        viewer=tracker.viewer(),
    )
    # Linear relates the issues only once it exists, so an unknown one must be caught beforehand.
    for related in draft.related():
        _ = tracker.read_issue(related)
    return tracker.create_issue(new)
