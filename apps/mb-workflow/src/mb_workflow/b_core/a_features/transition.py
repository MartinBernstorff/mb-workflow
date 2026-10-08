from typing import TYPE_CHECKING

from safe_result import Err, Ok

from mb_workflow.b_core.b_domain_services.flow_transition import FlowTransition
from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManagerError
from mb_workflow.b_core.d_domain_model.flow import (
    EventNames,
    FlowError,
    ReviewChart,
    WorkflowChart,
)

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
    from mb_workflow.b_core.d_domain_model.flow import EventName, StateName
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
    from mb_workflow.b_core.d_domain_model.pull_request import PrNumber
    from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses
    from mb_workflow.b_core.d_domain_model.workspace import Worktree


# A worktree for my own ticket follows the workflow chart and moves its ticket with it. A worktree
# reviewing a teammate's pull request follows the review chart, and only its board moves.
class WorktreeTransition:
    @staticmethod
    def move_worktree(
        *,
        board_at: Callable[[Worktree], WorkspaceStatusStore],
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
            else WorktreeTransition.worktree_linked_to(manager, ticket)
        )
        if isinstance(located, Err):
            return located
        worktree = located.value
        store = board_at(worktree)
        review_events = EventNames.of_chart(ReviewChart)
        reviewed = worktree.reviewed_pull_request()
        if reviewed is not None:
            return WorktreeTransition.move_review(
                store=store,
                worktree=worktree,
                pr=reviewed,
                review_events=review_events,
                event=event,
                force=force,
            )
        if event in review_events.root and event not in EventNames.of_chart(WorkflowChart).root:
            return Err(WorktreeTransition.not_a_review(worktree, event))
        return FlowTransition.move_ticket(
            chart=WorkflowChart,
            store=store,
            tracker=tracker,
            issue=worktree.linked_issue(),
            wanted=wanted,
            statuses=statuses,
            event=event,
            force=force,
        )

    @staticmethod
    def move_review(
        *,
        store: WorkspaceStatusStore,
        worktree: Worktree,
        pr: PrNumber,
        review_events: EventNames,
        event: EventName,
        force: Force,
    ) -> Result[StateName, FlowError | WorkspaceManagerError]:
        if event not in review_events.root:
            taken = ", ".join(name.root for name in review_events.root)
            return Err(
                FlowError(
                    f"{worktree.path.root} reviews PR #{pr.root}, which has no ticket of yours,"
                    f" so {event.root} does not apply. A review worktree takes: {taken}."
                )
            )
        return FlowTransition.move_board(chart=ReviewChart, store=store, event=event, force=force)

    @staticmethod
    def not_a_review(worktree: Worktree, event: EventName) -> FlowError:
        linked = (
            "is linked to no pull request"
            if worktree.issue is None
            else f"is linked to your own ticket {worktree.issue.root}"
        )
        return FlowError(
            f"{worktree.path.root} {linked}, so {event.root} does not apply. It applies only to"
            " worktrees reviewing a teammate's pull request."
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
