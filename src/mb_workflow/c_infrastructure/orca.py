import logging
from subprocess import CalledProcessError
from typing import TYPE_CHECKING

from mb_workflow.b_core.d_domain_model.git import Ref
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
from mb_workflow.b_core.d_domain_model.pull_request import PrNumber, PrTitle
from mb_workflow.b_core.d_domain_model.workspace import (
    OpenedWorktree,
    ProjectSelector,
    RepoId,
    TerminalHandle,
    WorkspaceError,
    WorkspaceStatus,
    Worktree,
    WorktreeName,
    WorktreePath,
    Worktrees,
)
from mb_workflow.c_infrastructure.shell import Command, CommandOutput, Shell
from mb_workflow.d_lib.models import Payload, Value

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.directory import ExistingDirectory
    from mb_workflow.b_core.d_domain_model.workspace import AgentName, TerminalText, TimeoutMs

logger = logging.getLogger(__name__)


class OrcaError(WorkspaceError):
    pass


class WorktreeComment(Value[str]):
    @staticmethod
    def fake() -> WorktreeComment:
        return WorktreeComment.of(PrNumber.fake(), PrTitle.fake())

    @staticmethod
    def of(pr: PrNumber, title: PrTitle) -> WorktreeComment:
        return WorktreeComment(f"PR #{pr.root} — {title.root}")


class WorktreeSelector(Value[str]):
    @staticmethod
    def fake() -> WorktreeSelector:
        return WorktreeSelector.of(WorktreePath.fake())

    @staticmethod
    def of(path: WorktreePath) -> WorktreeSelector:
        return WorktreeSelector(f"path:{path.root}")

    @staticmethod
    def current() -> WorktreeSelector:
        return WorktreeSelector("current")


class ColumnLabel(Value[str]):
    @staticmethod
    def fake() -> ColumnLabel:
        return ColumnLabel("Implementing")

    @staticmethod
    def unknown() -> ColumnLabel:
        return ColumnLabel("mb-workflow-asks-which-columns-exist")

    def assignment(self, worktree: WorktreeSelector) -> Command:
        return status_assignment(worktree, self)


def status_assignment(worktree: WorktreeSelector, column: ColumnLabel | WorkspaceStatus) -> Command:
    return Command(
        (
            "orca",
            "worktree",
            "set",
            "--worktree",
            worktree.root,
            "--workspace-status",
            column.root,
            "--json",
        )
    )


class ErrorMessage(Value[str]):
    @staticmethod
    def fake() -> ErrorMessage:
        return ErrorMessage("repo_not_found")


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


class OrcaWorktree(Payload):
    repo_id: RepoId
    path: WorktreePath
    display_name: WorktreeName | None = None
    project_id: ProjectSelector | None = None
    branch: Ref | None = None
    linked_issue: PrNumber | None = None
    linked_linear_issue: IssueIdentifier | None = None
    workspace_status: WorkspaceStatus | None = None

    @staticmethod
    def fake() -> OrcaWorktree:
        return OrcaWorktree(
            repo_id=RepoId.fake(),
            path=WorktreePath.fake(),
            display_name=WorktreeName.fake(),
            project_id=ProjectSelector.fake(),
            branch=Ref.fake(),
            linked_issue=PrNumber.fake(),
            linked_linear_issue=IssueIdentifier.fake(),
            workspace_status=WorkspaceStatus.fake(),
        )

    def domain(self) -> Worktree:
        return Worktree(
            repo=self.repo_id,
            path=self.path,
            name=self.display_name,
            project=self.project_id,
            branch=self.branch,
            pull_request=self.linked_issue,
            issue=self.linked_linear_issue,
            status=self.workspace_status,
        )


class WorktreeList(Payload):
    worktrees: tuple[OrcaWorktree, ...]

    @staticmethod
    def fake() -> WorktreeList:
        return WorktreeList(worktrees=(OrcaWorktree.fake(),))

    @staticmethod
    def parse(output: CommandOutput) -> Worktrees:
        listed = Envelope[WorktreeList].model_validate_json(output.root).unwrap()
        return Worktrees(tuple(worktree.domain() for worktree in listed.worktrees))


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
    worktree: OrcaWorktree
    agent_terminal_handle: TerminalHandle | None = None
    startup_terminal: StartupTerminal | None = None

    @staticmethod
    def fake() -> SingleWorktree:
        return SingleWorktree(
            worktree=OrcaWorktree.fake(),
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

    def opened(self) -> OpenedWorktree:
        return OpenedWorktree(worktree=self.worktree.domain(), terminal=self.terminal())


def single_worktree(output: CommandOutput) -> Worktree:
    return SingleWorktree.parse(output).worktree.domain()


def acknowledged(output: CommandOutput) -> Acknowledgement:
    return Envelope[Acknowledgement].model_validate_json(output.root).unwrap()


class Orca:
    def __init__(self, shell: Shell) -> None:
        self._shell = shell
        _ = shell.run(Command(("orca", "--version")))

    def where(self) -> ExistingDirectory:
        return self._shell.cwd()

    def current(self) -> Worktree:
        return single_worktree(self._run(Command(("orca", "worktree", "current", "--json"))))

    def worktrees(self) -> Worktrees:
        return WorktreeList.parse(self._run(Command(("orca", "worktree", "list", "--json"))))

    # Orca suffixes a clashing name rather than refusing it, so the refusal the port promises lives here.
    def create_for_review(
        self, repo: RepoId, pr: PrNumber, title: PrTitle, status: WorkspaceStatus
    ) -> WorktreePath:
        name = WorktreeName.of(pr)
        self.worktrees().in_repo(repo).refuse_duplicate(name)
        return single_worktree(
            self._run(
                Command(
                    (
                        "orca",
                        "worktree",
                        "create",
                        "--repo",
                        f"id:{repo.root}",
                        "--name",
                        name.root,
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
        ).path

    def create_for_issue(
        self,
        project: ProjectSelector,
        name: WorktreeName,
        issue: IssueIdentifier | None,
        agent: AgentName | None,
    ) -> OpenedWorktree:
        self.worktrees().in_project(project).refuse_duplicate(name)
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
        return SingleWorktree.parse(self._run(Command(tuple(command)))).opened()

    def wait_for_idle(self, terminal: TerminalHandle, timeout: TimeoutMs) -> None:
        try:
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
        except CalledProcessError as failed:
            raise OrcaError(f"{terminal.root} never went idle: {failed.stderr}") from failed

    def send_text(self, terminal: TerminalHandle, text: TerminalText) -> None:
        _ = self._shell.run(
            Command(("orca", "terminal", "send", "--terminal", terminal.root, "--text", text.root))
        )

    # Orca has no command that lists board columns, so its refusal of an unknown one carries the list.
    def columns(self, unknown: ColumnLabel) -> ErrorMessage:
        output = self._run(unknown.assignment(WorktreeSelector.current()))
        return Envelope[Acknowledgement].model_validate_json(output.root).refusal()

    def set_status(self, path: WorktreePath, status: WorkspaceStatus) -> None:
        _ = single_worktree(self._run(status_assignment(WorktreeSelector.of(path), status)))

    def remove(self, path: WorktreePath) -> None:
        _ = acknowledged(
            self._run(
                Command(
                    (
                        "orca",
                        "worktree",
                        "rm",
                        "--worktree",
                        WorktreeSelector.of(path).root,
                        "--force",
                        "--json",
                    )
                )
            )
        )

    # Orca exits non-zero on a refusal but still reports why in the JSON envelope on stdout.
    def _run(self, command: Command) -> CommandOutput:
        try:
            return self._shell.run(command)
        except CalledProcessError as refused:
            return CommandOutput(refused.stdout)
