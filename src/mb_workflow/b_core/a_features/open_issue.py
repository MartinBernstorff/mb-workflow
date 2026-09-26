import logging
from typing import TYPE_CHECKING

from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTrackerError
from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManagerError
from mb_workflow.b_core.d_domain_model.issue import (
    BranchSlug,
    IssueIdentifier,
    IssueState,
)
from mb_workflow.b_core.d_domain_model.workspace import (
    AgentName,
    TerminalText,
    TimeoutMs,
    WorktreeName,
)
from mb_workflow.d_lib.models import Model, Value

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManager
    from mb_workflow.b_core.d_domain_model.config import WorkspaceSettings
    from mb_workflow.b_core.d_domain_model.workspace import OpenedWorktree

logger = logging.getLogger(__name__)


class UnprefixedStateError(Exception):
    pass


class PromptUndeliveredError(Exception):
    pass


class PromptPrefix(Value[str]):
    @staticmethod
    def fake() -> PromptPrefix:
        return PromptPrefix("/implement")

    @staticmethod
    def of(state: IssueState) -> PromptPrefix:
        prefixes = {
            IssueState.backlog: PromptPrefix("/grill"),
            IssueState.maturing: PromptPrefix("/to-ticket"),
            IssueState.todo: PromptPrefix("/implement"),
        }
        prefix = prefixes.get(state)
        if prefix is None:
            raise UnprefixedStateError(f"No prompt prefix for an issue in {state}.")
        return prefix

    def applied(self, prompt: TerminalText) -> TerminalText:
        return TerminalText(f"{self.root} {prompt.root}")


class OpenRequest(Model):
    branch: BranchSlug
    issue: IssueIdentifier | None
    prompt: TerminalText | None
    idle_timeout: TimeoutMs

    @staticmethod
    def fake() -> OpenRequest:
        return OpenRequest(
            branch=BranchSlug.fake(),
            issue=IssueIdentifier.fake(),
            prompt=TerminalText.fake(),
            idle_timeout=TimeoutMs.fake(),
        )

    def agent(self) -> AgentName | None:
        return AgentName.claude() if self.prompt is not None else None

    def prefixed(self, state: IssueState | None) -> OpenRequest:
        if self.prompt is None or state is None:
            return self
        return self.model_copy(update={"prompt": PromptPrefix.of(state).applied(self.prompt)})


def open_workspace(
    manager: WorkspaceManager,
    tracker: TicketTracker,
    workspace: WorkspaceSettings,
    request: OpenRequest,
) -> None:
    # Assignment is a convenience, not the point of opening a workspace, so never fail the run over it.
    if request.issue is not None:
        try:
            tracker.assign(request.issue, workspace.assignee)
        except TicketTrackerError as error:
            logger.warning(
                "Could not assign %s to %s: %s",
                request.issue.root,
                workspace.assignee.root,
                error,
            )

    # Resolve the prompt before creating anything, so an unprefixable state leaves no half-open workspace.
    prompting = request.prefixed(issue_state(tracker, request.issue))

    name = WorktreeName.of_branch(request.branch, request.issue)
    logger.info("Creating worktree with name: %s", name.root)
    opened = manager.create_for_issue(workspace.orca_project, name, request.issue, request.agent())
    logger.info("Created %s", opened.worktree.path.root)

    send_prompt(manager, opened, prompting)


def issue_state(tracker: TicketTracker, issue: IssueIdentifier | None) -> IssueState | None:
    if issue is None:
        return None
    try:
        read = tracker.read_issue(issue)
    except TicketTrackerError as error:
        logger.warning("Could not read the state of %s: %s", issue.root, error)
        return None
    state = read.state()
    if state is None:
        logger.warning("%s has the unrecognised status %s.", issue.root, read.status.root)
    return state


def send_prompt(manager: WorkspaceManager, opened: OpenedWorktree, request: OpenRequest) -> None:
    if request.prompt is None:
        return

    if opened.terminal is None:
        raise PromptUndeliveredError("No agent terminal handle returned; prompt not typed.")

    try:
        manager.wait_for_idle(opened.terminal, request.idle_timeout)
    except WorkspaceManagerError:
        logger.warning("Agent terminal never went idle; typing the prompt anyway.")

    # Type the prompt without Enter so it can be tweaked before submitting.
    manager.send_text(opened.terminal, request.prompt)
