from typing import TYPE_CHECKING

from safe_result import Err

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
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import (
        WorkspaceManager,
        WorkspaceManagerError,
    )
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
    ) -> Result[
        StateName,
        FlowError | TicketTrackerError | MissingFlowLabelsError | WorkspaceManagerError,
    ]:
        here = manager.current()
        if isinstance(here, Err):
            return here
        return FlowTransition.move_ticket(
            chart=WorkflowChart,
            store=store,
            tracker=tracker,
            issue=here.value.linked_issue(),
            wanted=wanted,
            statuses=statuses,
            event=event,
            force=force,
        )
