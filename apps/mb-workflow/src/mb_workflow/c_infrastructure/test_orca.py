from subprocess import CalledProcessError
from typing import TYPE_CHECKING, override

from safe_result import Err, Ok

from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManagerError
from mb_workflow.b_core.d_domain_model.git import BranchName
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
from mb_workflow.b_core.d_domain_model.pull_request import PrNumber
from mb_workflow.b_core.d_domain_model.workspace import (
    DisplayName,
    RepoId,
    Submit,
    TerminalHandle,
    TerminalText,
    TimeoutMs,
    WorkspaceStatus,
    WorktreeName,
    WorktreePath,
)
from mb_workflow.c_infrastructure.orca import (
    Acknowledgement,
    ColumnLabel,
    Envelope,
    ErrorMessage,
    Orca,
    SingleWorktree,
    WorktreeComment,
    WorktreeList,
    WorktreeSelector,
    refusal_of,
    status_assignment,
)
from mb_workflow.c_infrastructure.shell import (
    Command,
    CommandOutput,
    CommandRunner,
    ExistingDirectory,
    Shell,
)
from mb_workflow.d_lib.models import Value

if TYPE_CHECKING:
    from pathlib import Path


def test_parses_worktree_list() -> None:
    output = CommandOutput(
        '{"id":"x","ok":true,"result":{"worktrees":['
        '{"repoId":"ed089d5b-6f96-45d2-ad3a-c2131bb3be91",'
        '"path":"/Users/me/orca/workspaces/mb-workflow/pr-1234",'
        '"branch":"refs/heads/feat/review-workspaces","linkedIssue":1234,'
        '"isArchived":false}]},"_meta":{"runtimeId":"y"}}'
    )
    parsed = WorktreeList.parse(output).unwrap().root[0]
    assert parsed.repo == RepoId.fake()
    assert parsed.path == WorktreePath.fake()
    assert parsed.branch is not None
    assert parsed.branch.branch() == BranchName.fake()
    assert parsed.pull_request == PrNumber.fake()


def test_parses_the_linked_linear_issue() -> None:
    output = CommandOutput(
        '{"ok":true,"result":{"worktrees":[{"repoId":"r","path":"/tmp/x",'
        '"linkedLinearIssue":"E-4289"}]}}'
    )
    assert WorktreeList.parse(output).unwrap().root[0].issue == IssueIdentifier.fake()


def test_worktree_without_branch_or_issue_parses() -> None:
    output = CommandOutput(
        '{"ok":true,"result":{"worktrees":[{"repoId":"r","path":"/tmp/x",'
        '"branch":null,"linkedIssue":null}]}}'
    )
    parsed = WorktreeList.parse(output).unwrap().root[0]
    assert parsed.branch is None
    assert parsed.pull_request is None
    assert parsed.issue is None


def test_envelope_failure_surfaces_orca_message() -> None:
    output = CommandOutput('{"ok":false,"error":{"code":"repo_not_found","message":"nope"}}')
    assert WorktreeList.parse(output) == Err(WorkspaceManagerError("nope"))


def test_reads_the_created_worktree() -> None:
    output = CommandOutput(
        '{"ok":true,"result":{"worktree":{"repoId":"r","path":'
        f'"{WorktreePath.fake().root}","workspaceStatus":"{WorkspaceStatus.fake().root}"'
        '},"warnings":[]}}'
    )
    created = SingleWorktree.parse(output).unwrap().opened().worktree
    assert (created.path, created.status) == (WorktreePath.fake(), WorkspaceStatus.fake())


def test_acknowledges_a_removal() -> None:
    output = CommandOutput('{"ok":true,"result":{"removed":true}}')
    assert Acknowledgement.parse(output) == Ok(Acknowledgement())


def test_worktree_name_and_comment_describe_the_pr() -> None:
    assert WorktreeName.of(PrNumber.fake()) == WorktreeName.fake()
    assert WorktreeComment.of(PrNumber.fake()).root == "PR #1234"


def test_parses_the_display_name() -> None:
    output = CommandOutput(
        '{"ok":true,"result":{"worktrees":[{"repoId":"r","path":"/tmp/x",'
        f'"displayName":"{DisplayName.fake().root}"}}]}}}}'
    )
    assert WorktreeList.parse(output).unwrap().root[0].display_name == DisplayName.fake()


def test_prefers_the_agent_terminal_handle() -> None:
    output = CommandOutput(
        '{"ok":true,"result":{"worktree":{"repoId":"r","path":"/tmp/x"},'
        '"agentTerminalHandle":"agent-1","startupTerminal":{"handle":"startup-1"}}}'
    )
    assert SingleWorktree.parse(output).unwrap().terminal() == TerminalHandle("agent-1")


def test_falls_back_to_the_startup_terminal_handle() -> None:
    output = CommandOutput(
        '{"ok":true,"result":{"worktree":{"repoId":"r","path":"/tmp/x"},'
        '"startupTerminal":{"handle":"startup-1"}}}'
    )
    assert SingleWorktree.parse(output).unwrap().terminal() == TerminalHandle("startup-1")


def test_a_worktree_created_without_an_agent_has_no_terminal() -> None:
    output = CommandOutput('{"ok":true,"result":{"worktree":{"repoId":"r","path":"/tmp/x"}}}')
    assert SingleWorktree.parse(output).unwrap().terminal() is None


def test_moving_a_workspace_names_its_column_by_id() -> None:
    assert status_assignment(WorktreeSelector.fake(), WorkspaceStatus.fake()).root == (
        "orca",
        "worktree",
        "set",
        "--worktree",
        WorktreeSelector.fake().root,
        "--workspace-status",
        "status-8",
        "--json",
    )


def test_asks_which_columns_exist_by_naming_one_that_cannot() -> None:
    assert status_assignment(WorktreeSelector.current(), ColumnLabel.unknown()).root == (
        "orca",
        "worktree",
        "set",
        "--worktree",
        "current",
        "--workspace-status",
        "mb-workflow-asks-which-columns-exist",
        "--json",
    )


def test_a_refusal_carries_the_message_orca_gave() -> None:
    output = CommandOutput(
        '{"ok":false,"error":{"code":"invalid_argument","message":"Unknown workspace status."}}'
    )
    envelope = Envelope[Acknowledgement].model_validate_json(output.root)
    assert envelope.refusal() == Ok(ErrorMessage("Unknown workspace status."))


def test_a_command_orca_accepted_holds_no_refusal() -> None:
    output = CommandOutput('{"ok":true,"result":{}}')
    envelope = Envelope[Acknowledgement].model_validate_json(output.root)
    refused = envelope.refusal()
    assert isinstance(refused, Err)
    assert "meant to refuse" in str(refused.error)


def test_a_failed_command_carries_the_reason_orca_printed() -> None:
    refused = CalledProcessError(
        1, ("orca",), '{"ok":false,"error":{"code":"x","message":"selector_not_found"}}', ""
    )
    assert refusal_of(refused) == ErrorMessage("selector_not_found")


def test_a_failed_command_without_an_envelope_carries_the_exit() -> None:
    refused = CalledProcessError(1, ("orca",), "not json", "")
    assert refusal_of(refused) == ErrorMessage(
        "Command '('orca',)' returned non-zero exit status 1."
    )


def test_an_unreadable_reply_is_a_workspace_manager_error() -> None:
    unreadable = Acknowledgement.parse(CommandOutput("not json"))
    assert isinstance(unreadable, Err)
    assert "unreadable reply" in str(unreadable.error)


class OrcaReason(Value[str]):
    @staticmethod
    def fake() -> OrcaReason:
        return OrcaReason("orca is down")


# Answers every command with one shell script, run through the real shell, as orca would.
class ScriptedOrca(CommandRunner):
    def __init__(self, directory: ExistingDirectory, script: Command) -> None:
        self._shell = Shell(directory)
        self._script = script

    @staticmethod
    def refusing(directory: ExistingDirectory, reason: OrcaReason) -> ScriptedOrca:
        reply = f'{{"ok":false,"error":{{"code":"x","message":"{reason.root}"}}}}'
        return ScriptedOrca(directory, Command(("sh", "-c", f"printf '%s' '{reply}'; exit 1")))

    @staticmethod
    def unreadable(directory: ExistingDirectory) -> ScriptedOrca:
        return ScriptedOrca(directory, Command(("sh", "-c", "printf 'not json'")))

    @staticmethod
    def missing(directory: ExistingDirectory) -> ScriptedOrca:
        return ScriptedOrca(directory, Command(("mb-workflow-no-such-orca",)))

    @override
    def cwd(self) -> ExistingDirectory:
        return self._shell.cwd()

    @override
    def at(self, directory: ExistingDirectory) -> ScriptedOrca:
        return ScriptedOrca(directory, self._script)

    @override
    def run(self, command: Command) -> CommandOutput:
        return self._shell.run(self._script)


def test_connecting_to_a_failing_orca_is_refused(tmp_path: Path) -> None:
    reason = OrcaReason.fake()
    connected = Orca.connected(ScriptedOrca.refusing(ExistingDirectory(tmp_path), reason))
    assert connected == Err(WorkspaceManagerError(reason.root))


def test_connecting_to_a_missing_orca_is_refused(tmp_path: Path) -> None:
    connected = Orca.connected(ScriptedOrca.missing(ExistingDirectory(tmp_path)))
    assert connected == Err(WorkspaceManagerError("orca is not installed or not on PATH."))


def test_a_refusing_orca_is_returned_as_a_workspace_manager_error(tmp_path: Path) -> None:
    reason = OrcaReason.fake()
    orca = Orca(ScriptedOrca.refusing(ExistingDirectory(tmp_path), reason))
    path = WorktreePath.fake()
    terminal = TerminalHandle.fake()
    results = (
        orca.current(),
        orca.worktrees(),
        orca.create_for_review(RepoId.fake(), PrNumber.fake(), WorkspaceStatus.fake(), None),
        orca.remove(path),
        orca.set_status(path, WorkspaceStatus.fake()),
        orca.set_display_name(path, DisplayName.fake()),
        orca.set_linked_issue(path, IssueIdentifier.fake()),
        orca.wait_for_idle(terminal, TimeoutMs.fake()),
        orca.send_text(terminal, TerminalText.fake(), Submit.fake()),
    )
    for result in results:
        assert result == Err(WorkspaceManagerError(reason.root))


def test_an_unreadable_orca_reply_is_returned_as_a_workspace_manager_error(
    tmp_path: Path,
) -> None:
    orca = Orca(ScriptedOrca.unreadable(ExistingDirectory(tmp_path)))
    path = WorktreePath.fake()
    results = (
        orca.current(),
        orca.worktrees(),
        orca.create_for_review(RepoId.fake(), PrNumber.fake(), WorkspaceStatus.fake(), None),
        orca.remove(path),
        orca.set_status(path, WorkspaceStatus.fake()),
        orca.set_display_name(path, DisplayName.fake()),
        orca.set_linked_issue(path, IssueIdentifier.fake()),
    )
    for result in results:
        assert isinstance(result, Err)
        assert "unreadable reply" in str(result.error)
