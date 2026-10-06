from subprocess import CalledProcessError
from typing import TYPE_CHECKING, override

from assertions import Assert
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
    WorkspacePriority,
    WorkspaceStatus,
    WorktreeName,
    WorktreePath,
)
from mb_workflow.c_infrastructure.orca import (
    Acknowledgement,
    ColumnLabel,
    ErrorMessage,
    Orca,
    SingleWorktree,
    WorktreeComment,
    WorktreeList,
    WorktreeSelector,
    orca_refusal,
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
    Assert.that(parsed.repo).matches(RepoId.fake())
    Assert.that(parsed.path).matches(WorktreePath.fake())
    branch = Assert.that(parsed.branch).exists()
    Assert.that(branch.branch()).matches(BranchName.fake())
    Assert.that(parsed.pull_request).matches(PrNumber.fake())


def test_parses_the_linked_linear_issue() -> None:
    output = CommandOutput(
        '{"ok":true,"result":{"worktrees":[{"repoId":"r","path":"/tmp/x",'
        '"linkedLinearIssue":"E-4289"}]}}'
    )
    Assert.that(WorktreeList.parse(output).unwrap().root[0].issue).matches(IssueIdentifier.fake())


def test_worktree_without_branch_or_issue_parses() -> None:
    output = CommandOutput(
        '{"ok":true,"result":{"worktrees":[{"repoId":"r","path":"/tmp/x",'
        '"branch":null,"linkedIssue":null}]}}'
    )
    parsed = WorktreeList.parse(output).unwrap().root[0]
    Assert.that(parsed.branch).matches(None)
    Assert.that(parsed.pull_request).matches(None)
    Assert.that(parsed.issue).matches(None)


def test_envelope_failure_surfaces_orca_message() -> None:
    message = "nope"
    output = CommandOutput(
        f'{{"ok":false,"error":{{"code":"repo_not_found","message":"{message}"}}}}'
    )
    Assert.that(WorktreeList.parse(output)).matches(Err(WorkspaceManagerError(message)))


def test_reads_the_created_worktree() -> None:
    output = CommandOutput(
        '{"ok":true,"result":{"worktree":{"repoId":"r","path":'
        f'"{WorktreePath.fake().root}","workspaceStatus":"{WorkspaceStatus.fake().root}"'
        '},"warnings":[]}}'
    )
    created = SingleWorktree.parse(output).unwrap().opened().worktree
    Assert.that((created.path, created.status)).matches(
        (WorktreePath.fake(), WorkspaceStatus.fake())
    )


def test_acknowledges_a_removal() -> None:
    output = CommandOutput('{"ok":true,"result":{"removed":true}}')
    Assert.that(Acknowledgement.parse(output)).matches(Ok(Acknowledgement()))


def test_worktree_name_and_comment_describe_the_pr() -> None:
    comment = "PR #1234"
    Assert.that(WorktreeName.of(PrNumber.fake())).matches(WorktreeName.fake())
    Assert.that(WorktreeComment.of(PrNumber.fake()).root).matches(comment)


def test_parses_the_display_name() -> None:
    output = CommandOutput(
        '{"ok":true,"result":{"worktrees":[{"repoId":"r","path":"/tmp/x",'
        f'"displayName":"{DisplayName.fake().root}"}}]}}}}'
    )
    Assert.that(WorktreeList.parse(output).unwrap().root[0].display_name).matches(
        DisplayName.fake()
    )


def test_parses_the_priority() -> None:
    output = CommandOutput(
        '{"ok":true,"result":{"worktrees":[{"repoId":"r","path":"/tmp/x",'
        f'"priority":"{WorkspacePriority.fake().value}"}}]}}}}'
    )
    Assert.that(WorktreeList.parse(output).unwrap().root[0].priority).matches(
        WorkspacePriority.fake()
    )


def test_an_unprioritised_worktree_parses() -> None:
    output = CommandOutput(
        '{"ok":true,"result":{"worktrees":[{"repoId":"r","path":"/tmp/x","priority":null}]}}'
    )
    Assert.that(WorktreeList.parse(output).unwrap().root[0].priority).matches(None)


def test_prefers_the_agent_terminal_handle() -> None:
    agent = TerminalHandle("agent-1")
    output = CommandOutput(
        '{"ok":true,"result":{"worktree":{"repoId":"r","path":"/tmp/x"},'
        f'"agentTerminalHandle":"{agent.root}","startupTerminal":{{"handle":"startup-1"}}}}}}'
    )
    Assert.that(SingleWorktree.parse(output).unwrap().terminal()).matches(agent)


def test_falls_back_to_the_startup_terminal_handle() -> None:
    startup = TerminalHandle("startup-1")
    output = CommandOutput(
        '{"ok":true,"result":{"worktree":{"repoId":"r","path":"/tmp/x"},'
        f'"startupTerminal":{{"handle":"{startup.root}"}}}}}}'
    )
    Assert.that(SingleWorktree.parse(output).unwrap().terminal()).matches(startup)


def test_a_worktree_created_without_an_agent_has_no_terminal() -> None:
    output = CommandOutput('{"ok":true,"result":{"worktree":{"repoId":"r","path":"/tmp/x"}}}')
    Assert.that(SingleWorktree.parse(output).unwrap().terminal()).matches(None)


def test_moving_a_workspace_names_its_column_by_id() -> None:
    Assert.that(status_assignment(WorktreeSelector.fake(), WorkspaceStatus.fake()).root).matches(
        (
            "orca",
            "worktree",
            "set",
            "--worktree",
            WorktreeSelector.fake().root,
            "--workspace-status",
            "status-8",
            "--json",
        )
    )


def test_asks_which_columns_exist_by_naming_one_that_cannot() -> None:
    Assert.that(status_assignment(WorktreeSelector.current(), ColumnLabel.unknown()).root).matches(
        (
            "orca",
            "worktree",
            "set",
            "--worktree",
            "current",
            "--workspace-status",
            "mb-workflow-asks-which-columns-exist",
            "--json",
        )
    )


def test_a_refusal_carries_the_message_orca_gave() -> None:
    message = ErrorMessage("Unknown workspace status.")
    output = CommandOutput(
        f'{{"ok":false,"error":{{"code":"invalid_argument","message":"{message.root}"}}}}'
    )
    Assert.that(orca_refusal(output)).matches(Ok(message))


def test_a_command_orca_accepted_holds_no_refusal() -> None:
    output = CommandOutput('{"ok":true,"result":{}}')
    phrase = "meant to refuse"
    refused = orca_refusal(output)
    error = Assert.that(refused).is_err(Exception)
    Assert.that(str(error)).contains(phrase)


def test_a_failed_command_carries_the_reason_orca_printed() -> None:
    reason = ErrorMessage("selector_not_found")
    refused = CalledProcessError(
        1, ("orca",), f'{{"ok":false,"error":{{"code":"x","message":"{reason.root}"}}}}', ""
    )
    Assert.that(refusal_of(refused)).matches(reason)


def test_a_failed_command_without_an_envelope_carries_the_exit() -> None:
    refused = CalledProcessError(1, ("orca",), "not json", "")
    exit_message = ErrorMessage("Command '('orca',)' returned non-zero exit status 1.")
    Assert.that(refusal_of(refused)).matches(exit_message)


def test_an_unreadable_reply_is_a_workspace_manager_error() -> None:
    phrase = "unreadable reply"
    unreadable = Acknowledgement.parse(CommandOutput("not json"))
    error = Assert.that(unreadable).is_err(WorkspaceManagerError)
    Assert.that(str(error)).contains(phrase)


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
    Assert.that(connected).matches(Err(WorkspaceManagerError(reason.root)))


def test_connecting_to_a_missing_orca_is_refused(tmp_path: Path) -> None:
    refusal = WorkspaceManagerError("orca is not installed or not on PATH.")
    connected = Orca.connected(ScriptedOrca.missing(ExistingDirectory(tmp_path)))
    Assert.that(connected).matches(Err(refusal))


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
        orca.set_priority(path, WorkspacePriority.fake()),
        orca.wait_for_idle(terminal, TimeoutMs.fake()),
        orca.send_text(terminal, TerminalText.fake(), Submit.fake()),
    )
    for result in results:
        Assert.that(result).matches(Err(WorkspaceManagerError(reason.root)))


def test_an_unreadable_orca_reply_is_returned_as_a_workspace_manager_error(
    tmp_path: Path,
) -> None:
    phrase = "unreadable reply"
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
        orca.set_priority(path, WorkspacePriority.fake()),
    )
    for result in results:
        error = Assert.that(result).is_err(WorkspaceManagerError)
        Assert.that(str(error)).contains(phrase)
