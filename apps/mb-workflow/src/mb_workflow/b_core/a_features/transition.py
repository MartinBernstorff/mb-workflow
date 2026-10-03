from typing import TYPE_CHECKING

from mb_workflow.b_core.b_domain_services.flow_transition import FlowTransition
from mb_workflow.b_core.d_domain_model.flow import WorkflowChart

if TYPE_CHECKING:
    from safe_result import Result

    from mb_workflow.b_core.b_domain_services.flow_label_check import MissingFlowLabelsError
    from mb_workflow.b_core.b_domain_services.flow_transition import Force
    from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
        TicketTracker,
        TicketTrackerError,
    )
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManager
    from mb_workflow.b_core.d_domain_model.flow import EventName, FlowError, StateName
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses


# Moves the ticket linked to the worktree you stand in.
class LinkedTicketTransition:
    @staticmethod
    def move_linked_ticket(
        *,
        store: WorkspaceStatusStore,
        tracker: TicketTracker,
        manager: WorkspaceManager,
        wanted: FlowLabels,
        statuses: TicketStatuses,
        event: EventName,
        force: Force,
    ) -> Result[StateName, FlowError | TicketTrackerError | MissingFlowLabelsError]:
        issue = manager.current().linked_issue()
        return FlowTransition.move_ticket(
            chart=WorkflowChart,
            store=store,
            tracker=tracker,
            issue=issue,
            wanted=wanted,
            statuses=statuses,
            event=event,
            force=force,
        )
