from typing import TYPE_CHECKING

from mb_workflow.b_core.b_domain_services import flow_transition
from mb_workflow.b_core.d_domain_model.flow import EventName, StateName, WorkflowChart

if TYPE_CHECKING:
    from safe_result import Result

    from mb_workflow.b_core.b_domain_services.flow_label_check import MissingFlowLabelsError
    from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
        TicketTracker,
        TicketTrackerError,
    )
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManager
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses


class LinkedTicketTransition:
    @staticmethod
    def transition_linked_ticket(
        *,
        store: WorkspaceStatusStore,
        tracker: TicketTracker,
        manager: WorkspaceManager,
        wanted: FlowLabels,
        statuses: TicketStatuses,
        event: EventName,
        force: flow_transition.Force,
    ) -> Result[StateName, TicketTrackerError | MissingFlowLabelsError]:
        issue = manager.current().linked_issue()
        return flow_transition.FlowTransition.transition_issue(
            chart=WorkflowChart,
            store=store,
            tracker=tracker,
            issue=issue,
            wanted=wanted,
            statuses=statuses,
            event=event,
            force=force,
        )
