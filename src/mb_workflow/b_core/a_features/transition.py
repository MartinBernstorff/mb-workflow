from typing import TYPE_CHECKING

from mb_workflow.b_core.b_domain_services import flow_transition
from mb_workflow.b_core.d_domain_model.flow import EventName, StateName, WorkflowChart

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManager
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
    from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses
    from mb_workflow.b_core.d_domain_model.workspace import Worktree


class UnlinkedWorktreeError(Exception):
    pass


def issue_from_workspace(worktree: Worktree) -> IssueIdentifier:
    if worktree.issue is None:
        raise UnlinkedWorktreeError(
            f"{worktree.path.root} has no linked Linear issue. Link one with `mw link <ticket>`."
        )
    return worktree.issue


def transition(
    *,
    store: WorkspaceStatusStore,
    tracker: TicketTracker,
    manager: WorkspaceManager,
    wanted: FlowLabels,
    statuses: TicketStatuses,
    event: EventName,
    force: flow_transition.Force,
) -> StateName:
    issue = issue_from_workspace(manager.current())
    return flow_transition.transition(
        chart=WorkflowChart,
        store=store,
        tracker=tracker,
        issue=issue,
        wanted=wanted,
        statuses=statuses,
        event=event,
        force=force,
    )
