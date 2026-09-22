import logging
from subprocess import CalledProcessError
from typing import TYPE_CHECKING

from mb_workflow.a_presentation.console import ExitCode
from mb_workflow.b_core.d_domain_model.issue import BranchSlug, IssueIdentifier
from mb_workflow.c_infrastructure.linear import Assignee, IssueState, Linear
from mb_workflow.c_infrastructure.orca import (
    AgentName,
    Orca,
    OrcaError,
    ProjectSelector,
    SingleWorktree,
    TerminalText,
    TimeoutMs,
    WorktreeName,
)
from mb_workflow.d_lib.models import Model, Value

if TYPE_CHECKING:
    from mb_workflow.c_infrastructure.shell import Shell

logger = logging.getLogger(__name__)


class UnprefixedStateError(Exception):
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

    def prefixed(self, state: IssueState | None) -> OpenRequest:
        if self.prompt is None or state is None:
            return self
        return self.model_copy(update={"prompt": PromptPrefix.of(state).applied(self.prompt)})


def open_issue(shell: Shell, request: OpenRequest) -> ExitCode:
    try:
        return open_workspace(Orca(shell), Linear(shell), request)
    except FileNotFoundError as error:
        logger.error("%s is not installed or not on PATH.", error.filename)
        return ExitCode(1)
    except (CalledProcessError, OrcaError, UnprefixedStateError) as error:
        logger.error("%s", error)
        return ExitCode(1)


def open_workspace(orca: Orca, linear: Linear, request: OpenRequest) -> ExitCode:
    # Assignment is a convenience, not the point of opening a workspace, so never fail the run over it.
    if request.issue is not None:
        failure = linear.assign(request.issue, request.assignee)
        if failure is not None:
            logger.warning(
                "Could not assign %s to %s: %s",
                request.issue.root,
                request.assignee.root,
                failure.root,
            )

    # Resolve the prompt before creating anything, so an unprefixable state leaves no half-open workspace.
    prompting = request.prefixed(issue_state(linear, request.issue))

    name = WorktreeName.of_branch(request.branch, request.issue)
    logger.info("Creating worktree with name: %s", name.root)
    worktree = orca.create_for_issue(request.project, name, request.issue, request.agent())
    logger.info("Created %s", worktree.worktree.path.root)

    return send_prompt(orca, worktree, prompting)


def issue_state(linear: Linear, issue: IssueIdentifier | None) -> IssueState | None:
    return linear.state(issue) if issue is not None else None


def send_prompt(orca: Orca, worktree: SingleWorktree, request: OpenRequest) -> ExitCode:
    if request.prompt is None:
        return ExitCode(0)

    terminal = worktree.terminal()
    if terminal is None:
        logger.error("No agent terminal handle returned; prompt not typed.")
        return ExitCode(1)

    try:
        orca.wait_for_idle(terminal, request.idle_timeout)
    except CalledProcessError:
        logger.warning("Agent terminal never went idle; typing the prompt anyway.")

    # Type the prompt without Enter so it can be tweaked before submitting.
    orca.send_text(terminal, request.prompt)
    return ExitCode(0)
