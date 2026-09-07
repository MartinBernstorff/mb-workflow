import logging
import re
from subprocess import CalledProcessError

from mb_workflow.linear import Assignee, BranchSlug, IssueIdentifier, Linear
from mb_workflow.models import Model
from mb_workflow.orca import (
    AgentName,
    Orca,
    OrcaError,
    ProjectSelector,
    SingleWorktree,
    TerminalText,
    TimeoutMs,
    WorktreeName,
)
from mb_workflow.shell import ExitCode, Shell

logger = logging.getLogger(__name__)


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


def worktree_name(branch: BranchSlug, issue: IssueIdentifier | None) -> WorktreeName:
    slug = branch.root or (issue.root if issue is not None else "linear-workspace")
    # Orca prefixes the branch with the git user, so hand it the unprefixed slug.
    name = slug.split("/", 1)[-1]
    # Linear prefixes the slug with the issue identifier ("e-4289-..."), which orca shows on its own.
    name = re.sub(r"^[A-Za-z]+-\d+-", "", name)
    # Linear slugifies "fix(ci): ..." to "fixci-...", so drop the conventional-commit type and scope.
    name = re.sub(
        r"^(?:feat|fix|chore|refactor|revert|perf|docs|test|build|style|ci)[a-z]*-(?=.)", "", name
    )
    return WorktreeName(name)


def open_issue(shell: Shell, request: OpenRequest) -> ExitCode:
    try:
        return opened(Orca(shell), Linear(shell), request)
    except FileNotFoundError as error:
        logger.error("%s is not installed or not on PATH.", error.filename)
        return ExitCode(1)
    except (CalledProcessError, OrcaError) as error:
        logger.error("%s", error)
        return ExitCode(1)


def opened(orca: Orca, linear: Linear, request: OpenRequest) -> ExitCode:
    if request.issue is not None:
        linear.assign(request.issue, request.assignee)

    name = worktree_name(request.branch, request.issue)
    logger.info("Creating worktree with name: %s", name.root)
    worktree = orca.create_for_issue(request.project, name, request.issue, request.agent())
    logger.info("Created %s", worktree.worktree.path.root)

    return typed(orca, worktree, request)


def typed(orca: Orca, worktree: SingleWorktree, request: OpenRequest) -> ExitCode:
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
