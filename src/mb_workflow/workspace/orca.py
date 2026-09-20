import logging
import re
from pathlib import Path
from subprocess import CalledProcessError
from typing import TYPE_CHECKING

from mb_workflow.git import Ref
from mb_workflow.issue import IssueIdentifier
from mb_workflow.models import Payload, Value
from mb_workflow.pull_request import PrNumber, PrTitle
from mb_workflow.shell import Command, CommandOutput, ExistingDirectory, Shell

if TYPE_CHECKING:
    from mb_workflow.issue import BranchSlug

logger = logging.getLogger(__name__)


class OrcaError(Exception):
    pass


class RepoId(Value[str]):
    @staticmethod
    def fake() -> RepoId:
        return RepoId("ed089d5b-6f96-45d2-ad3a-c2131bb3be91")


class WorktreeName(Value[str]):
    @staticmethod
    def fake() -> WorktreeName:
        return WorktreeName(f"pr-{PrNumber.fake().root}")

    @staticmethod
    def of(pr: PrNumber) -> WorktreeName:
        return WorktreeName(f"pr-{pr.root}")

    @staticmethod
    def of_branch(branch: BranchSlug, issue: IssueIdentifier | None) -> WorktreeName:
        slug = branch.root or (issue.root if issue is not None else "linear-workspace")
        # Orca prefixes the branch with the git user, so hand it the unprefixed slug.
        name = slug.split("/", 1)[-1]
        # Linear prefixes the slug with the issue identifier ("e-4289-..."), which orca shows on its own.
        name = re.sub(r"^[A-Za-z]+-\d+-", "", name)
        # Linear slugifies "fix(ci): ..." to "fixci-...", so drop the conventional-commit type and scope.
        name = re.sub(
            r"^(?:feat|fix|chore|refactor|revert|perf|docs|test|build|style|ci)[a-z]*-(?=.)",
            "",
            name,
        )
        return WorktreeName(name)


class WorktreeComment(Value[str]):
    @staticmethod
    def fake() -> WorktreeComment:
        return WorktreeComment.of(PrNumber.fake(), PrTitle.fake())

    @staticmethod
    def of(pr: PrNumber, title: PrTitle) -> WorktreeComment:
        return WorktreeComment(f"PR #{pr.root} — {title.root}")


class WorkspaceStatus(Value[str]):
    @staticmethod
    def fake() -> WorkspaceStatus:
        return WorkspaceStatus("status-8")


class ColumnLabel(Value[str]):
    @staticmethod
    def fake() -> ColumnLabel:
        return ColumnLabel("Implementing")

    @staticmethod
    def unknown() -> ColumnLabel:
        return ColumnLabel("mb-workflow-asks-which-columns-exist")

    def assignment(self, worktree: WorktreeSelector) -> Command:
        return Command(
            (
                "orca",
                "worktree",
                "set",
                "--worktree",
                worktree.root,
                "--workspace-status",
                self.root,
                "--json",
            )
        )


class ErrorMessage(Value[str]):
    @staticmethod
    def fake() -> ErrorMessage:
        return ErrorMessage("repo_not_found")


class WorktreePath(Value[Path]):
    @staticmethod
    def fake() -> WorktreePath:
        return WorktreePath(Path("/Users/me/orca/workspaces/mb-workflow/pr-1234"))

    @staticmethod
    def of(directory: ExistingDirectory) -> WorktreePath:
        return WorktreePath(directory.root)

    def existing(self) -> ExistingDirectory:
        return ExistingDirectory(self.root)

    def selector(self) -> WorktreeSelector:
        return WorktreeSelector(f"path:{self.root}")


class ProjectSelector(Value[str]):
    @staticmethod
    def fake() -> ProjectSelector:
        return ProjectSelector("github:flowbasedk/flowbase")


class AgentName(Value[str]):
    @staticmethod
    def fake() -> AgentName:
        return AgentName.claude()

    @staticmethod
    def claude() -> AgentName:
        return AgentName("claude")


class TerminalHandle(Value[str]):
    @staticmethod
    def fake() -> TerminalHandle:
        return TerminalHandle("terminal-1")


class TerminalText(Value[str]):
    @staticmethod
    def fake() -> TerminalText:
        return TerminalText("Implement the issue.")


class TimeoutMs(Value[int]):
    @staticmethod
    def fake() -> TimeoutMs:
        return TimeoutMs(60000)


class WorktreeSelector(Value[str]):
    @staticmethod
    def fake() -> WorktreeSelector:
        return WorktreeSelector(f"path:{WorktreePath.fake().root}")

    @staticmethod
    def current() -> WorktreeSelector:
        return WorktreeSelector("current")


class EnvelopeError(Payload):
    message: ErrorMessage

    @staticmethod
    def fake() -> EnvelopeError:
        return EnvelopeError(message=ErrorMessage.fake())


class Succeeded(Value[bool]):
    @staticmethod
    def fake() -> Succeeded:
        return Succeeded(True)


class Envelope[T](Payload):
    ok: Succeeded
    result: T | None = None
    error: EnvelopeError | None = None

    def refusal(self) -> ErrorMessage:
        if self.ok.root or self.error is None:
            raise OrcaError("orca accepted a value it was meant to refuse")
        return self.error.message

    def unwrap(self) -> T:
        if self.result is None or not self.ok.root:
            raise OrcaError(
                self.error.message.root if self.error is not None else "orca returned no result"
            )
        return self.result


class Worktree(Payload):
    repo_id: RepoId
    path: WorktreePath
    branch: Ref | None = None
    linked_issue: PrNumber | None = None
    linked_linear_issue: IssueIdentifier | None = None
    workspace_status: WorkspaceStatus | None = None

    @staticmethod
    def fake() -> Worktree:
        return Worktree(
            repo_id=RepoId.fake(),
            path=WorktreePath.fake(),
            branch=Ref.fake(),
            linked_issue=PrNumber.fake(),
            linked_linear_issue=IssueIdentifier.fake(),
            workspace_status=WorkspaceStatus.fake(),
        )


class WorktreeList(Payload):
    worktrees: tuple[Worktree, ...]

    @staticmethod
    def fake() -> WorktreeList:
        return WorktreeList(worktrees=(Worktree.fake(),))


class Acknowledgement(Payload):
    @staticmethod
    def fake() -> Acknowledgement:
        return Acknowledgement()


class StartupTerminal(Payload):
    handle: TerminalHandle | None = None

    @staticmethod
    def fake() -> StartupTerminal:
        return StartupTerminal(handle=TerminalHandle.fake())


class SingleWorktree(Payload):
    worktree: Worktree
    agent_terminal_handle: TerminalHandle | None = None
    startup_terminal: StartupTerminal | None = None

    @staticmethod
    def fake() -> SingleWorktree:
        return SingleWorktree(
            worktree=Worktree.fake(),
            agent_terminal_handle=TerminalHandle.fake(),
            startup_terminal=StartupTerminal.fake(),
        )

    @staticmethod
    def parse(output: CommandOutput) -> SingleWorktree:
        return Envelope[SingleWorktree].model_validate_json(output.root).unwrap()

    def terminal(self) -> TerminalHandle | None:
        if self.agent_terminal_handle is not None:
            return self.agent_terminal_handle
        return self.startup_terminal.handle if self.startup_terminal is not None else None


class Worktrees(Value[tuple[Worktree, ...]]):
    @staticmethod
    def fake() -> Worktrees:
        return Worktrees((Worktree.fake(),))

    @staticmethod
    def parse(output: CommandOutput) -> Worktrees:
        envelope = Envelope[WorktreeList].model_validate_json(output.root)
        return Worktrees(envelope.unwrap().worktrees)

    def repo_id_at(self, directory: ExistingDirectory) -> RepoId:
        wanted = directory.root.resolve()
        for worktree in self.root:
            if worktree.path.root.resolve() == wanted:
                return worktree.repo_id
        raise OrcaError(f"{wanted} is not an Orca-managed worktree")


def created_path(output: CommandOutput) -> ExistingDirectory:
    return SingleWorktree.parse(output).worktree.path.existing()


def single_worktree(output: CommandOutput) -> Worktree:
    return SingleWorktree.parse(output).worktree


def acknowledged(output: CommandOutput) -> Acknowledgement:
    return Envelope[Acknowledgement].model_validate_json(output.root).unwrap()


class Orca:
    def __init__(self, shell: Shell) -> None:
        self._shell = shell
        _ = shell.run(Command(("orca", "--version")))

    def where(self) -> ExistingDirectory:
        return self._shell.cwd()

    def current(self) -> Worktree:
        return single_worktree(self._shell.run(Command(("orca", "worktree", "current", "--json"))))

    def worktrees(self) -> Worktrees:
        return Worktrees.parse(self._shell.run(Command(("orca", "worktree", "list", "--json"))))

    def create_worktree(
        self, repo: RepoId, pr: PrNumber, title: PrTitle, status: WorkspaceStatus
    ) -> ExistingDirectory:
        return created_path(
            self._shell.run(
                Command(
                    (
                        "orca",
                        "worktree",
                        "create",
                        "--repo",
                        f"id:{repo.root}",
                        "--name",
                        WorktreeName.of(pr).root,
                        "--no-parent",
                        "--issue",
                        str(pr.root),
                        "--comment",
                        WorktreeComment.of(pr, title).root,
                        "--workspace-status",
                        status.root,
                        "--json",
                    )
                )
            )
        )

    def create_for_issue(
        self,
        project: ProjectSelector,
        name: WorktreeName,
        issue: IssueIdentifier | None,
        agent: AgentName | None,
    ) -> SingleWorktree:
        command = [
            "orca",
            "worktree",
            "create",
            "--project",
            project.root,
            "--name",
            name.root,
            "--activate",
            "--no-parent",
            "--json",
        ]
        if issue is not None:
            command += ["--linear-issue", issue.root]
        if agent is not None:
            command += ["--agent", agent.root]
        return SingleWorktree.parse(self._shell.run(Command(tuple(command))))

    def wait_for_idle(self, terminal: TerminalHandle, timeout: TimeoutMs) -> None:
        _ = self._shell.run(
            Command(
                (
                    "orca",
                    "terminal",
                    "wait",
                    "--terminal",
                    terminal.root,
                    "--for",
                    "tui-idle",
                    "--timeout-ms",
                    str(timeout.root),
                )
            )
        )

    def send_text(self, terminal: TerminalHandle, text: TerminalText) -> None:
        _ = self._shell.run(
            Command(("orca", "terminal", "send", "--terminal", terminal.root, "--text", text.root))
        )

    # Orca has no command that lists board columns, so its refusal of an unknown one carries the list.
    def columns(self, unknown: ColumnLabel) -> ErrorMessage:
        command = unknown.assignment(WorktreeSelector.current())
        try:
            output = self._shell.run(command)
        except CalledProcessError as refused:
            output = CommandOutput(refused.stdout)
        return Envelope[Acknowledgement].model_validate_json(output.root).refusal()

    def set_status(self, worktree: WorktreeSelector, column: ColumnLabel) -> None:
        _ = single_worktree(self._shell.run(column.assignment(worktree)))

    def remove_worktree(self, path: WorktreePath) -> None:
        _ = acknowledged(
            self._shell.run(
                Command(
                    (
                        "orca",
                        "worktree",
                        "rm",
                        "--worktree",
                        path.selector().root,
                        "--force",
                        "--json",
                    )
                )
            )
        )
