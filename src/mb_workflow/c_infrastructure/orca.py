import logging
from contextlib import contextmanager
from subprocess import CalledProcessError
from typing import TYPE_CHECKING, override

from pydantic import ValidationError

from mb_workflow.b_core.c_secondary_ports.workspace_manager import (
    WorkspaceManager,
    WorkspaceManagerError,
)
from mb_workflow.b_core.d_domain_model.git import Ref
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
from mb_workflow.b_core.d_domain_model.pull_request import PrNumber
from mb_workflow.b_core.d_domain_model.workspace import (
    DisplayName,
    OpenedWorktree,
    RepoId,
    TerminalHandle,
    WorkspaceStatus,
    Worktree,
    WorktreeName,
    WorktreePath,
    Worktrees,
)
from mb_workflow.c_infrastructure.shell import Command, CommandOutput, Shell
from mb_workflow.d_lib.models import Payload, Value

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from mb_workflow.b_core.d_domain_model.workspace import (
        AgentName,
        ProjectSelector,
        Submit,
        TerminalText,
        TimeoutMs,
    )

logger = logging.getLogger(__name__)


class WorktreeComment(Value[str]):
    @staticmethod
    def fake() -> WorktreeComment:
        return WorktreeComment.of(PrNumber.fake())

    @staticmethod
    def of(pr: PrNumber) -> WorktreeComment:
        return WorktreeComment(f"PR #{pr.root}")


class ColumnLabel(Value[str]):
    @staticmethod
    def fake() -> ColumnLabel:
        return ColumnLabel("Implementing")

    @staticmethod
    def unknown() -> ColumnLabel:
        return ColumnLabel("mb-workflow-asks-which-columns-exist")


class ErrorMessage(Value[str]):
    @staticmethod
    def fake() -> ErrorMessage:
        return ErrorMessage("repo_not_found")


class WorktreeSelector(Value[str]):
    @staticmethod
    def fake() -> WorktreeSelector:
        return WorktreeSelector.of(WorktreePath.fake())

    @staticmethod
    def current() -> WorktreeSelector:
        return WorktreeSelector("current")

    @staticmethod
    def of(path: WorktreePath) -> WorktreeSelector:
        return WorktreeSelector(f"path:{path.root}")


def status_assignment(worktree: WorktreeSelector, column: WorkspaceStatus | ColumnLabel) -> Command:
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
            raise WorkspaceManagerError("orca accepted a value it was meant to refuse")
        return self.error.message

    def unwrap(self) -> T:
        if self.result is None or not self.ok.root:
            raise WorkspaceManagerError(
                self.error.message.root if self.error is not None else "orca returned no result"
            )
        return self.result


class WorktreePayload(Payload):
    repo_id: RepoId
    path: WorktreePath
    branch: Ref | None = None
    linked_issue: PrNumber | None = None
    linked_linear_issue: IssueIdentifier | None = None
    workspace_status: WorkspaceStatus | None = None
    display_name: DisplayName | None = None

    @staticmethod
    def fake() -> WorktreePayload:
        return WorktreePayload(
            repo_id=RepoId.fake(),
            path=WorktreePath.fake(),
            branch=Ref.fake(),
            linked_issue=PrNumber.fake(),
            linked_linear_issue=IssueIdentifier.fake(),
            workspace_status=WorkspaceStatus.fake(),
            display_name=DisplayName.fake(),
        )

    def worktree(self) -> Worktree:
        return Worktree(
            repo=self.repo_id,
            path=self.path,
            branch=self.branch,
            pull_request=self.linked_issue,
            issue=self.linked_linear_issue,
            status=self.workspace_status,
            display_name=self.display_name,
        )


class WorktreeList(Payload):
    worktrees: tuple[WorktreePayload, ...]

    @staticmethod
    def fake() -> WorktreeList:
        return WorktreeList(worktrees=(WorktreePayload.fake(),))

    @staticmethod
    def parse(output: CommandOutput) -> Worktrees:
        listed = Envelope[WorktreeList].model_validate_json(output.root).unwrap()
        return Worktrees(tuple(worktree.worktree() for worktree in listed.worktrees))


class Acknowledgement(Payload):
    @staticmethod
    def fake() -> Acknowledgement:
        return Acknowledgement()

    @staticmethod
    def parse(output: CommandOutput) -> Acknowledgement:
        return Envelope[Acknowledgement].model_validate_json(output.root).unwrap()


class StartupTerminal(Payload):
    handle: TerminalHandle | None = None

    @staticmethod
    def fake() -> StartupTerminal:
        return StartupTerminal(handle=TerminalHandle.fake())


class SingleWorktree(Payload):
    worktree: WorktreePayload
    agent_terminal_handle: TerminalHandle | None = None
    startup_terminal: StartupTerminal | None = None

    @staticmethod
    def fake() -> SingleWorktree:
        return SingleWorktree(
            worktree=WorktreePayload.fake(),
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
        return OpenedWorktree(worktree=self.worktree.worktree(), terminal=self.terminal())


# Orca exits non-zero on a refusal but still prints the envelope, whose message says why.
def refusal_of(error: CalledProcessError) -> ErrorMessage:
    try:
        return Envelope[Acknowledgement].model_validate_json(error.stdout).refusal()
    except ValidationError, WorkspaceManagerError, TypeError:
        return ErrorMessage(str(error))


@contextmanager
def translated_errors() -> Generator[None]:
    try:
        yield
    except CalledProcessError as error:
        raise WorkspaceManagerError(refusal_of(error).root) from error
    except ValidationError as error:
        raise WorkspaceManagerError(f"orca printed an unreadable reply: {error}") from error


class Orca(WorkspaceManager):
    def __init__(self, shell: Shell) -> None:
        self._shell = shell
        _ = shell.run(Command(("orca", "--version")))

    @override
    def current(self) -> Worktree:
        return self._single(Command(("orca", "worktree", "current", "--json"))).worktree.worktree()

    @override
    def worktrees(self) -> Worktrees:
        return self._parsed(Command(("orca", "worktree", "list", "--json")), WorktreeList.parse)

    @override
    def create_for_review(self, repo: RepoId, pr: PrNumber, status: WorkspaceStatus) -> Worktree:
        return self._single(
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
                    WorktreeComment.of(pr).root,
                    "--workspace-status",
                    status.root,
                    "--json",
                )
            )
        ).worktree.worktree()

    @override
    def create_for_issue(
        self,
        project: ProjectSelector,
        name: WorktreeName,
        issue: IssueIdentifier | None,
        agent: AgentName | None,
        status: WorkspaceStatus | None,
    ) -> OpenedWorktree:
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
        if status is not None:
            command += ["--workspace-status", status.root]
        return self._single(Command(tuple(command))).opened()

    @override
    def remove(self, path: WorktreePath) -> None:
        _ = self._parsed(
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
            ),
            Acknowledgement.parse,
        )

    @override
    def set_status(self, path: WorktreePath, status: WorkspaceStatus) -> None:
        _ = self._single(status_assignment(WorktreeSelector.of(path), status))

    @override
    def set_display_name(self, path: WorktreePath, name: DisplayName) -> None:
        _ = self._single(
            Command(
                (
                    "orca",
                    "worktree",
                    "set",
                    "--worktree",
                    WorktreeSelector.of(path).root,
                    "--display-name",
                    name.root,
                    "--json",
                )
            )
        )

    @override
    def wait_for_idle(self, terminal: TerminalHandle, timeout: TimeoutMs) -> None:
        _ = self._run(
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

    @override
    def send_text(self, terminal: TerminalHandle, text: TerminalText, submit: Submit) -> None:
        command = ("orca", "terminal", "send", "--terminal", terminal.root, "--text", text.root)
        _ = self._run(Command((*command, "--enter") if submit.root else command))

    def columns(self, unknown: ColumnLabel) -> ErrorMessage:
        listed = self.worktrees().root
        if not listed:
            raise WorkspaceManagerError(
                "Orca manages no worktree to read the board's columns through."
            )
        command = status_assignment(WorktreeSelector.of(listed[0].path), unknown)
        try:
            output = self._shell.run(command)
        except CalledProcessError as refused:
            output = CommandOutput(refused.stdout)
        return Envelope[Acknowledgement].model_validate_json(output.root).refusal()

    def _single(self, command: Command) -> SingleWorktree:
        return self._parsed(command, SingleWorktree.parse)

    def _parsed[T](self, command: Command, parse: Callable[[CommandOutput], T]) -> T:
        with translated_errors():
            return parse(self._shell.run(command))

    def _run(self, command: Command) -> CommandOutput:
        with translated_errors():
            return self._shell.run(command)
