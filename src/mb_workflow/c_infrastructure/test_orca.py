from subprocess import CalledProcessError

import pytest

from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManagerError
from mb_workflow.b_core.d_domain_model.git import BranchName
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
from mb_workflow.b_core.d_domain_model.pull_request import PrNumber
from mb_workflow.b_core.d_domain_model.workspace import (
    RepoId,
    TerminalHandle,
    WorkspaceStatus,
    WorktreeName,
    WorktreePath,
)
from mb_workflow.c_infrastructure.orca import (
    Acknowledgement,
    ColumnLabel,
    Envelope,
    ErrorMessage,
    SingleWorktree,
    WorktreeComment,
    WorktreeList,
    WorktreeSelector,
    refusal_of,
    status_assignment,
)
from mb_workflow.c_infrastructure.shell import CommandOutput


def test_parses_worktree_list() -> None:
    output = CommandOutput(
        '{"id":"x","ok":true,"result":{"worktrees":['
        '{"repoId":"ed089d5b-6f96-45d2-ad3a-c2131bb3be91",'
        '"path":"/Users/me/orca/workspaces/mb-workflow/pr-1234",'
        '"branch":"refs/heads/feat/review-workspaces","linkedIssue":1234,'
        '"isArchived":false}]},"_meta":{"runtimeId":"y"}}'
    )
    parsed = WorktreeList.parse(output).root[0]
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
    assert WorktreeList.parse(output).root[0].issue == IssueIdentifier.fake()


def test_worktree_without_branch_or_issue_parses() -> None:
    output = CommandOutput(
        '{"ok":true,"result":{"worktrees":[{"repoId":"r","path":"/tmp/x",'
        '"branch":null,"linkedIssue":null}]}}'
    )
    parsed = WorktreeList.parse(output).root[0]
    assert parsed.branch is None
    assert parsed.pull_request is None
    assert parsed.issue is None


def test_envelope_failure_surfaces_orca_message() -> None:
    output = CommandOutput('{"ok":false,"error":{"code":"repo_not_found","message":"nope"}}')
    with pytest.raises(WorkspaceManagerError, match="nope"):
        _ = WorktreeList.parse(output)


def test_reads_the_created_worktree() -> None:
    output = CommandOutput(
        '{"ok":true,"result":{"worktree":{"repoId":"r","path":'
        f'"{WorktreePath.fake().root}","workspaceStatus":"{WorkspaceStatus.fake().root}"'
        '},"warnings":[]}}'
    )
    created = SingleWorktree.parse(output).opened().worktree
    assert (created.path, created.status) == (WorktreePath.fake(), WorkspaceStatus.fake())


def test_acknowledges_a_removal() -> None:
    output = CommandOutput('{"ok":true,"result":{"removed":true}}')
    assert Acknowledgement.parse(output) == Acknowledgement()


def test_a_worktree_is_selected_by_its_own_path() -> None:
    assert WorktreeSelector.of(WorktreePath.fake()) == WorktreeSelector(
        f"path:{WorktreePath.fake().root}"
    )


def test_worktree_name_and_comment_describe_the_pr() -> None:
    assert WorktreeName.of(PrNumber.fake()) == WorktreeName.fake()
    assert WorktreeComment.fake().root == "PR #1234 — Add review workspaces"


def test_prefers_the_agent_terminal_handle() -> None:
    output = CommandOutput(
        '{"ok":true,"result":{"worktree":{"repoId":"r","path":"/tmp/x"},'
        '"agentTerminalHandle":"agent-1","startupTerminal":{"handle":"startup-1"}}}'
    )
    assert SingleWorktree.parse(output).terminal() == TerminalHandle("agent-1")


def test_falls_back_to_the_startup_terminal_handle() -> None:
    output = CommandOutput(
        '{"ok":true,"result":{"worktree":{"repoId":"r","path":"/tmp/x"},'
        '"startupTerminal":{"handle":"startup-1"}}}'
    )
    assert SingleWorktree.parse(output).terminal() == TerminalHandle("startup-1")


def test_a_worktree_created_without_an_agent_has_no_terminal() -> None:
    output = CommandOutput('{"ok":true,"result":{"worktree":{"repoId":"r","path":"/tmp/x"}}}')
    assert SingleWorktree.parse(output).terminal() is None


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
    assert envelope.refusal() == ErrorMessage("Unknown workspace status.")


def test_a_command_orca_accepted_holds_no_refusal() -> None:
    output = CommandOutput('{"ok":true,"result":{}}')
    envelope = Envelope[Acknowledgement].model_validate_json(output.root)
    with pytest.raises(WorkspaceManagerError, match="meant to refuse"):
        _ = envelope.refusal()


def test_a_failed_command_carries_the_reason_orca_printed() -> None:
    refused = CalledProcessError(
        1, ("orca",), '{"ok":false,"error":{"code":"x","message":"selector_not_found"}}', ""
    )
    assert refusal_of(refused) == ErrorMessage("selector_not_found")


def test_a_failed_command_without_an_envelope_carries_the_exit() -> None:
    refused = CalledProcessError(1, ("orca",), "not json", "")
    assert refusal_of(refused) == ErrorMessage(str(refused))
