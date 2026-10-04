import logging
from subprocess import CalledProcessError
from typing import TYPE_CHECKING, override

from pydantic import ValidationError
from safe_result import Err, Ok, Result, safe_with

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
from mb_workflow.c_infrastructure.shell import Command, CommandOutput, CommandRunner
from mb_workflow.d_lib.models import Payload, Value

if TYPE_CHECKING:
    from collections.abc import Callable

    from mb_workflow.b_core.d_domain_model.workspace import (
        Activate,
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


class OrcaEnvelope[T](Payload):
    ok: Succeeded
    result: T | None = None
    error: EnvelopeError | None = None

    @staticmethod
    def read(
        envelope: type[OrcaEnvelope[T]], output: CommandOutput
    ) -> Result[OrcaEnvelope[T], WorkspaceManagerError]:
        match OrcaEnvelope._validated(envelope, output):
            case Ok(read):
                return Ok(read)
            case Err(error):
                return Err(WorkspaceManagerError(f"orca printed an unreadable reply: {error}"))

    @staticmethod
    @safe_with(ValidationError)
    def _validated(envelope: type[OrcaEnvelope[T]], output: CommandOutput) -> OrcaEnvelope[T]:
        return envelope.model_validate_json(output.root)

    def refusal(self) -> Result[ErrorMessage, WorkspaceManagerError]:
        if self.ok.root or self.error is None:
            return Err(WorkspaceManagerError("orca accepted a value it was meant to refuse"))
        return Ok(self.error.message)

    def answer(self) -> Result[T, WorkspaceManagerError]:
        if self.result is None or not self.ok.root:
            return Err(
                WorkspaceManagerError(
                    self.error.message.root if self.error is not None else "orca returned no result"
                )
            )
        return Ok(self.result)


def orca_reply[T](payload: type[T], output: CommandOutput) -> Result[T, WorkspaceManagerError]:
    match OrcaEnvelope.read(OrcaEnvelope[payload], output):
        case Ok(read):
            return read.answer()
        case Err() as unreadable:
            return unreadable


def orca_refusal(output: CommandOutput) -> Result[ErrorMessage, WorkspaceManagerError]:
    match OrcaEnvelope.read(OrcaEnvelope[Acknowledgement], output):
        case Ok(read):
            return read.refusal()
        case Err() as unreadable:
            return unreadable


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
    def parse(output: CommandOutput) -> Result[Worktrees, WorkspaceManagerError]:
        match orca_reply(WorktreeList, output):
            case Ok(listed):
                return Ok(Worktrees(tuple(worktree.worktree() for worktree in listed.worktrees)))
            case Err() as unreadable:
                return unreadable


class Acknowledgement(Payload):
    @staticmethod
    def fake() -> Acknowledgement:
        return Acknowledgement()

    @staticmethod
    def parse(output: CommandOutput) -> Result[Acknowledgement, WorkspaceManagerError]:
        return orca_reply(Acknowledgement, output)


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
    def parse(output: CommandOutput) -> Result[SingleWorktree, WorkspaceManagerError]:
        return orca_reply(SingleWorktree, output)

    def terminal(self) -> TerminalHandle | None:
        if self.agent_terminal_handle is not None:
            return self.agent_terminal_handle
        return self.startup_terminal.handle if self.startup_terminal is not None else None

    def opened(self) -> OpenedWorktree:
        return OpenedWorktree(worktree=self.worktree.worktree(), terminal=self.terminal())


def printed_by(error: CalledProcessError) -> CommandOutput:
    printed = error.stdout
    return CommandOutput(printed if isinstance(printed, str) else "")


def refusal_of(error: CalledProcessError) -> ErrorMessage:
    match orca_refusal(printed_by(error)):
        case Ok(message):
            return message
        case Err():
            return ErrorMessage(str(error))


class Orca(WorkspaceManager):
    def __init__(self, shell: CommandRunner) -> None:
        self._shell = shell

    @staticmethod
    def connected(shell: CommandRunner) -> Result[Orca, WorkspaceManagerError]:
        match Orca._probed(shell):
            case Ok(orca):
                return Ok(orca)
            case Err(CalledProcessError() as error):
                return Err(WorkspaceManagerError(refusal_of(error).root))
            case Err(FileNotFoundError()):
                return Err(WorkspaceManagerError("orca is not installed or not on PATH."))
            case Err(error):
                return Err(WorkspaceManagerError(f"Cannot run orca: {error}"))

    @staticmethod
    @safe_with(CalledProcessError, OSError)
    def _probed(shell: CommandRunner) -> Orca:
        _ = shell.run(Command(("orca", "--version")))
        return Orca(shell)

    @override
    def current(self) -> Result[Worktree, WorkspaceManagerError]:
        match self._single(Command(("orca", "worktree", "current", "--json"))):
            case Ok(single):
                return Ok(single.worktree.worktree())
            case Err() as failed:
                return failed

    @override
    def worktrees(self) -> Result[Worktrees, WorkspaceManagerError]:
        return self._parsed(Command(("orca", "worktree", "list", "--json")), WorktreeList.parse)

    @override
    def create_for_review(
        self, repo: RepoId, pr: PrNumber, status: WorkspaceStatus, agent: AgentName | None
    ) -> Result[OpenedWorktree, WorkspaceManagerError]:
        command = [
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
        ]
        if agent is not None:
            command += ["--agent", agent.root]
        return self._opened(Command(tuple(command)))

    @override
    def create_for_issue(
        self,
        project: ProjectSelector,
        name: WorktreeName,
        issue: IssueIdentifier | None,
        agent: AgentName | None,
        status: WorkspaceStatus | None,
        *,
        activate: Activate,
    ) -> Result[OpenedWorktree, WorkspaceManagerError]:
        command = [
            "orca",
            "worktree",
            "create",
            "--project",
            project.root,
            "--name",
            name.root,
            "--no-parent",
            "--json",
        ]
        if issue is not None:
            command += ["--linear-issue", issue.root]
        if agent is not None:
            command += ["--agent", agent.root]
        if status is not None:
            command += ["--workspace-status", status.root]
        if activate.root:
            command += ["--activate"]
        return self._opened(Command(tuple(command)))

    @override
    def remove(self, path: WorktreePath) -> Result[None, WorkspaceManagerError]:
        return Orca._discarded(
            self._parsed(
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
        )

    @override
    def set_status(
        self, path: WorktreePath, status: WorkspaceStatus
    ) -> Result[None, WorkspaceManagerError]:
        return Orca._discarded(self._single(status_assignment(WorktreeSelector.of(path), status)))

    @override
    def set_display_name(
        self, path: WorktreePath, name: DisplayName
    ) -> Result[None, WorkspaceManagerError]:
        return Orca._discarded(
            self._single(
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
        )

    @override
    def set_linked_issue(
        self, path: WorktreePath, issue: IssueIdentifier
    ) -> Result[None, WorkspaceManagerError]:
        return Orca._discarded(
            self._single(
                Command(
                    (
                        "orca",
                        "worktree",
                        "set",
                        "--worktree",
                        WorktreeSelector.of(path).root,
                        "--linear-issue",
                        issue.root,
                        "--json",
                    )
                )
            )
        )

    @override
    def wait_for_idle(
        self, terminal: TerminalHandle, timeout: TimeoutMs
    ) -> Result[None, WorkspaceManagerError]:
        return Orca._discarded(
            self._run(
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
        )

    @override
    def send_text(
        self, terminal: TerminalHandle, text: TerminalText, submit: Submit
    ) -> Result[None, WorkspaceManagerError]:
        command = ("orca", "terminal", "send", "--terminal", terminal.root, "--text", text.root)
        return Orca._discarded(
            self._run(Command((*command, "--enter") if submit.root else command))
        )

    def columns(self, unknown: ColumnLabel) -> Result[ErrorMessage, WorkspaceManagerError]:
        match self.worktrees():
            case Ok(listed):
                pass
            case Err() as failed:
                return failed
        if not listed.root:
            return Err(
                WorkspaceManagerError(
                    "Orca manages no worktree to read the board's columns through."
                )
            )
        command = status_assignment(WorktreeSelector.of(listed.root[0].path), unknown)
        match self._run_raising(command):
            case Ok(output):
                pass
            case Err(refused):
                output = printed_by(refused)
        return orca_refusal(output)

    def _opened(self, command: Command) -> Result[OpenedWorktree, WorkspaceManagerError]:
        match self._single(command):
            case Ok(single):
                return Ok(single.opened())
            case Err() as failed:
                return failed

    def _single(self, command: Command) -> Result[SingleWorktree, WorkspaceManagerError]:
        return self._parsed(command, SingleWorktree.parse)

    @staticmethod
    def _discarded[T](
        result: Result[T, WorkspaceManagerError],
    ) -> Result[None, WorkspaceManagerError]:
        match result:
            case Ok():
                return Ok(None)
            case Err() as failed:
                return failed

    def _parsed[T](
        self,
        command: Command,
        parse: Callable[[CommandOutput], Result[T, WorkspaceManagerError]],
    ) -> Result[T, WorkspaceManagerError]:
        match self._run(command):
            case Ok(output):
                return parse(output)
            case Err() as failed:
                return failed

    def _run(self, command: Command) -> Result[CommandOutput, WorkspaceManagerError]:
        match self._run_raising(command):
            case Ok(output):
                return Ok(output)
            case Err(error):
                return Err(WorkspaceManagerError(refusal_of(error).root))

    @safe_with(CalledProcessError)
    def _run_raising(self, command: Command) -> CommandOutput:
        return self._shell.run(command)
