import logging
from typing import TYPE_CHECKING

from mb_workflow.b_core.b_domain_services.next_action import next_action, state_of
from mb_workflow.b_core.c_secondary_ports.claims import (
    ClaimRequest,
    LabelledClaim,
    claim_ticket,
    label_claim_or_withdraw,
    require_claim_label,
)
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTrackerError
from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManagerError
from mb_workflow.b_core.d_domain_model.claim import ClaimHolder, HostName, TakeOver
from mb_workflow.b_core.d_domain_model.flow import (
    AwaitingHuman,
    Finished,
    FlowError,
    Skill,
    WorkflowChart,
)
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
from mb_workflow.b_core.d_domain_model.workspace import (
    AgentName,
    Submit,
    TerminalText,
    TimeoutMs,
    WorktreeName,
)
from mb_workflow.d_lib.models import Model

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.claims import ClaimRegistry
    from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManager
    from mb_workflow.b_core.d_domain_model.config import ClaimSettings, WorkspaceSettings
    from mb_workflow.b_core.d_domain_model.flow import StateName
    from mb_workflow.b_core.d_domain_model.workspace import OpenedWorktree

logger = logging.getLogger(__name__)


class PromptUndeliveredError(Exception):
    pass


class StartRequest(Model):
    ticket: IssueIdentifier
    submit: Submit
    idle_timeout: TimeoutMs
    host: HostName
    take_over: TakeOver

    @staticmethod
    def fake() -> StartRequest:
        return StartRequest(
            ticket=IssueIdentifier.fake(),
            submit=Submit.fake(),
            idle_timeout=TimeoutMs.fake(),
            host=HostName.fake(),
            take_over=TakeOver.fake(),
        )

    def prompt_for(self, action: Skill | AwaitingHuman) -> TerminalText | None:
        if isinstance(action, AwaitingHuman):
            return None
        return TerminalText(f"{action.root} {self.ticket.root}")


def start_ticket(
    *,
    manager: WorkspaceManager,
    tracker: TicketTracker,
    claims: ClaimRegistry,
    board: WorkspaceStatusStore,
    workspace: WorkspaceSettings,
    claim_settings: ClaimSettings,
    request: StartRequest,
) -> None:
    # Resolve the state before touching anything, so a ticket with no work left is neither claimed, assigned nor opened.
    status = tracker.read_issue(request.ticket).status
    state = state_of(WorkflowChart, status)
    prompt = request.prompt_for(action_in(state))

    name = WorktreeName.of_issue(request.ticket)
    holder = ClaimHolder(host=request.host, worktree=name)
    require_claim_label(tracker, claim_settings.label)
    claim_ticket(
        claims,
        ClaimRequest(
            ticket=request.ticket,
            status=status,
            holder=holder,
            take_over=request.take_over,
        ),
    )
    label_claim_or_withdraw(
        claims,
        tracker,
        LabelledClaim(ticket=request.ticket, holder=holder, label=claim_settings.label),
    )

    # Assignment is a convenience, not the point of starting a ticket, so never fail the run over it.
    try:
        tracker.assign(request.ticket, workspace.assignee)
    except TicketTrackerError as error:
        logger.warning(
            "Could not assign %s to %s: %s",
            request.ticket.root,
            workspace.assignee.root,
            error,
        )

    logger.info("Creating worktree with name: %s", name.root)
    opened = manager.create_for_issue(
        workspace.orca_project,
        name,
        request.ticket,
        None if prompt is None else AgentName.claude(),
        board.status_for(state),
    )
    logger.info("Created %s", opened.worktree.path.root)

    if prompt is not None:
        send_prompt(manager, opened, prompt, request.idle_timeout, request.submit)


def action_in(state: StateName) -> Skill | AwaitingHuman:
    action = next_action(WorkflowChart, state)
    if isinstance(action, Finished):
        raise FlowError(f"The ticket is {state.root}, so there is no work left in it.")
    if isinstance(action, AwaitingHuman):
        logger.warning(
            "The ticket is in %s, which waits for a human, so no prompt is typed.", state.root
        )
    return action


def send_prompt(
    manager: WorkspaceManager,
    opened: OpenedWorktree,
    prompt: TerminalText,
    idle_timeout: TimeoutMs,
    submit: Submit,
) -> None:
    if opened.terminal is None:
        raise PromptUndeliveredError("No agent terminal handle returned; prompt not typed.")

    try:
        manager.wait_for_idle(opened.terminal, idle_timeout)
    except WorkspaceManagerError:
        logger.warning("Agent terminal never went idle; typing the prompt anyway.")

    manager.send_text(opened.terminal, prompt, submit)
