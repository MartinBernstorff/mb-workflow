import logging
from typing import TYPE_CHECKING

from mb_workflow.b_core.b_domain_services.next_action import next_action, state_of
from mb_workflow.b_core.c_secondary_ports.issue_tracker import IssueTrackerError
from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManagerError
from mb_workflow.b_core.d_domain_model.flow import (
    AwaitingHuman,
    Finished,
    FlowError,
    Skill,
    WorkflowChart,
)
from mb_workflow.b_core.d_domain_model.issue import (
    Assignee,
    BranchSlug,
    IssueIdentifier,
)
from mb_workflow.b_core.d_domain_model.workspace import (
    AgentName,
    ProjectSelector,
    TerminalText,
    TimeoutMs,
    WorktreeName,
)
from mb_workflow.d_lib.models import Model

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.issue_tracker import IssueTracker
    from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManager
    from mb_workflow.b_core.d_domain_model.flow import StateName
    from mb_workflow.b_core.d_domain_model.workspace import OpenedWorktree

logger = logging.getLogger(__name__)


class PromptUndeliveredError(Exception):
    pass


class OpenRequest(Model):
    project: ProjectSelector
    branch: BranchSlug
    issue: IssueIdentifier | None
    prompt: TerminalText | None
    assignee: Assignee
    idle_timeout: TimeoutMs

    @staticmethod
    def fake() -> OpenRequest:
        return OpenRequest(
            project=ProjectSelector.fake(),
            branch=BranchSlug.fake(),
            issue=IssueIdentifier.fake(),
            prompt=TerminalText.fake(),
            assignee=Assignee.fake(),
            idle_timeout=TimeoutMs.fake(),
        )

    def agent(self) -> AgentName | None:
        return AgentName.claude() if self.prompt is not None else None

    def prompted_for(self, action: Skill | AwaitingHuman | None) -> OpenRequest:
        if self.prompt is None or action is None:
            return self
        if isinstance(action, AwaitingHuman):
            return self.model_copy(update={"prompt": None})
        return self.model_copy(update={"prompt": TerminalText(f"{action.root} {self.prompt.root}")})


def open_workspace(
    manager: WorkspaceManager,
    tracker: IssueTracker,
    board: WorkspaceStatusStore,
    request: OpenRequest,
) -> None:
    # Resolve the state before touching anything, so an issue with no work left is neither assigned nor opened.
    state = issue_state(tracker, request.issue)
    prompting = request.prompted_for(None if state is None else action_in(state))
    status = None if state is None else board.status_for(state)

    # Assignment is a convenience, not the point of opening a workspace, so never fail the run over it.
    if request.issue is not None:
        try:
            tracker.assign(request.issue, request.assignee)
        except IssueTrackerError as error:
            logger.warning(
                "Could not assign %s to %s: %s",
                request.issue.root,
                request.assignee.root,
                error,
            )

    name = WorktreeName.of_branch(request.branch, request.issue)
    logger.info("Creating worktree with name: %s", name.root)
    opened = manager.create_for_issue(
        request.project, name, request.issue, prompting.agent(), status
    )
    logger.info("Created %s", opened.worktree.path.root)

    send_prompt(manager, opened, prompting)


def action_in(state: StateName) -> Skill | AwaitingHuman:
    action = next_action(WorkflowChart, state)
    if isinstance(action, Finished):
        raise FlowError(f"The issue is {state.root}, so there is no work left in it.")
    if isinstance(action, AwaitingHuman):
        logger.warning(
            "The issue is in %s, which waits for a human, so no prompt is typed.", state.root
        )
    return action


def issue_state(tracker: IssueTracker, issue: IssueIdentifier | None) -> StateName | None:
    if issue is None:
        return None
    try:
        read = tracker.read_issue(issue)
    except IssueTrackerError as error:
        logger.warning("Could not read the state of %s: %s", issue.root, error)
        return None
    return state_of(WorkflowChart, read.status)


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
