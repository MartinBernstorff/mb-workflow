import logging
from typing import TYPE_CHECKING

from mb_workflow.b_core.b_domain_services.next_action import TicketState, next_action
from mb_workflow.b_core.b_domain_services.take_ticket import TicketTaking
from mb_workflow.b_core.c_secondary_ports.claims import ClaimRequest
from mb_workflow.b_core.c_secondary_ports.workspace_manager import (
    WorkspaceManagerError,
    set_display_name_or_warn,
)
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
    Activate,
    AgentName,
    DisplayName,
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
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
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
    activate: Activate

    @staticmethod
    def fake() -> StartRequest:
        return StartRequest(
            ticket=IssueIdentifier.fake(),
            submit=Submit.fake(),
            idle_timeout=TimeoutMs.fake(),
            host=HostName.fake(),
            take_over=TakeOver.fake(),
            activate=Activate.fake(),
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
    flow_labels: FlowLabels,
    request: StartRequest,
) -> None:
    detail = tracker.read_issue_detail(request.ticket)
    state = TicketState.state_with_work_left(WorkflowChart, flow_labels, detail.issue)
    prompt = request.prompt_for(action_in(request.ticket, state))

    name = WorktreeName.of_issue(request.ticket)
    TicketTaking.take_ticket(
        claims=claims,
        tracker=tracker,
        workspace=workspace,
        claim_settings=claim_settings,
        request=ClaimRequest(
            ticket=request.ticket,
            status=detail.issue.status,
            holder=ClaimHolder(host=request.host, worktree=name),
            take_over=request.take_over,
        ),
    )

    opened = manager.create_for_issue(
        workspace.orca_project,
        name,
        request.ticket,
        None if prompt is None else AgentName.claude(),
        board.status_for(state),
        activate=request.activate,
    )
    logger.info("Created worktree %s.", opened.worktree.path.root)
    set_display_name_or_warn(manager, opened.worktree.path, DisplayName.of_issue(detail.title))

    if prompt is not None:
        send_prompt(manager, opened, prompt, request.idle_timeout, request.submit)


def action_in(ticket: IssueIdentifier, state: StateName) -> Skill | AwaitingHuman:
    action = next_action(WorkflowChart, state)
    if isinstance(action, Finished):
        raise FlowError(f"The ticket is {state.root}, so there is no work left in it.")
    if isinstance(action, AwaitingHuman):
        logger.warning(
            "%s is in %s, which waits for a human, so no prompt is typed.",
            ticket.root,
            state.root,
        )
    else:
        logger.info("%s is in %s, so the next step is %s.", ticket.root, state.root, action.root)
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
    logger.info("%s %s.", "Submitted" if submit.root else "Typed", prompt.root)
