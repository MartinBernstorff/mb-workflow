from typing import TYPE_CHECKING

from safe_result import Err, Ok

from mb_workflow.b_core.b_domain_services.flow_transition import FlowTransition
from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManagerError
from mb_workflow.b_core.d_domain_model.flow import WorkflowChart

if TYPE_CHECKING:
    from collections.abc import Callable

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
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
    from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses
    from mb_workflow.b_core.d_domain_model.workspace import Worktree, WorktreePath


# Moves a ticket and the board column of the worktree linked to it: the named ticket, or the one
# linked to the worktree you stand in.
class LinkedTicketTransition:
    @staticmethod
    def move_linked_ticket(
        *,
        board_at: Callable[[WorktreePath], WorkspaceStatusStore],
        tracker: TicketTracker,
        manager: WorkspaceManager,
        wanted: FlowLabels,
        statuses: TicketStatuses,
        event: EventName,
        force: Force,
        ticket: IssueIdentifier | None,
    ) -> Result[
        StateName,
        FlowError | TicketTrackerError | MissingFlowLabelsError | WorkspaceManagerError,
    ]:
        located = (
            manager.current()
            if ticket is None
            else LinkedTicketTransition.worktree_linked_to(manager, ticket)
        )
        if isinstance(located, Err):
            return located
        return FlowTransition.move_ticket(
            chart=WorkflowChart,
            store=board_at(located.value.path),
            tracker=tracker,
            issue=located.value.linked_issue(),
            wanted=wanted,
            statuses=statuses,
            event=event,
            force=force,
        )

    @staticmethod
    def worktree_linked_to(
        manager: WorkspaceManager, ticket: IssueIdentifier
    ) -> Result[Worktree, WorkspaceManagerError]:
        listed = manager.worktrees()
        if isinstance(listed, Err):
            return listed
        linked = listed.value.linked_to(ticket)
        if linked is None:
            return Err(WorkspaceManagerError(f"No worktree is linked to {ticket.root}."))
        return Ok(linked)
