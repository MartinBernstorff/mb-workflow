import pytest

from mb_workflow.b_core.git import BranchName
from mb_workflow.b_core.issue import BranchSlug, IssueIdentifier
from mb_workflow.b_core.pull_request import PrNumber
from mb_workflow.c_infrastructure.orca import (
    Acknowledgement,
    ColumnLabel,
    Envelope,
    ErrorMessage,
    OrcaError,
    RepoId,
    SingleWorktree,
    TerminalHandle,
    WorktreeComment,
    WorktreeName,
    WorktreePath,
    Worktrees,
    WorktreeSelector,
    acknowledged,
    created_path,
)
from mb_workflow.c_infrastructure.shell import CommandOutput, ExistingDirectory


def test_parses_worktree_list() -> None:
    output = CommandOutput(
        '{"id":"x","ok":true,"result":{"worktrees":['
        '{"repoId":"ed089d5b-6f96-45d2-ad3a-c2131bb3be91",'
        '"path":"/Users/me/orca/workspaces/mb-workflow/pr-1234",'
        '"branch":"refs/heads/feat/review-workspaces","linkedIssue":1234,'
        '"isArchived":false}]},"_meta":{"runtimeId":"y"}}'
    )
    parsed = Worktrees.parse(output).root[0]
    assert parsed.repo_id == RepoId.fake()
    assert parsed.path == WorktreePath.fake()
    assert parsed.branch is not None
    assert parsed.branch.branch() == BranchName.fake()
    assert parsed.linked_issue == PrNumber.fake()


def test_parses_the_linked_linear_issue() -> None:
    output = CommandOutput(
        '{"ok":true,"result":{"worktrees":[{"repoId":"r","path":"/tmp/x",'
        '"linkedLinearIssue":"E-4289"}]}}'
    )
    assert Worktrees.parse(output).root[0].linked_linear_issue == IssueIdentifier.fake()


def test_worktree_without_branch_or_issue_parses() -> None:
    output = CommandOutput(
        '{"ok":true,"result":{"worktrees":[{"repoId":"r","path":"/tmp/x",'
        '"branch":null,"linkedIssue":null}]}}'
    )
    parsed = Worktrees.parse(output).root[0]
    assert parsed.branch is None
    assert parsed.linked_issue is None
    assert parsed.linked_linear_issue is None


def test_envelope_failure_surfaces_orca_message() -> None:
    output = CommandOutput('{"ok":false,"error":{"code":"repo_not_found","message":"nope"}}')
    with pytest.raises(OrcaError, match="nope"):
        _ = Worktrees.parse(output)


def test_reads_created_worktree_path() -> None:
    output = CommandOutput(
        '{"ok":true,"result":{"worktree":{"repoId":"r","path":'
        f'"{ExistingDirectory.fake().root}"'
        '},"warnings":[]}}'
    )
    assert created_path(output) == ExistingDirectory.fake()


def test_acknowledges_a_removal() -> None:
    output = CommandOutput('{"ok":true,"result":{"worktree":{"repoId":"r","path":"/tmp/x"}}}')
    assert acknowledged(output) is not None


def test_repo_id_at_matches_the_current_worktree() -> None:
    output = CommandOutput(
        '{"ok":true,"result":{"worktrees":[{"repoId":"other","path":"/tmp/elsewhere"},'
        f'{{"repoId":"{RepoId.fake().root}","path":"{ExistingDirectory.fake().root}"}}'
        "]}}"
    )
    assert Worktrees.parse(output).repo_id_at(ExistingDirectory.fake()) == RepoId.fake()


def test_repo_id_at_rejects_an_unmanaged_directory() -> None:
    output = CommandOutput('{"ok":true,"result":{"worktrees":[]}}')
    with pytest.raises(OrcaError, match="not an Orca-managed worktree"):
        _ = Worktrees.parse(output).repo_id_at(ExistingDirectory.fake())


def test_a_created_worktree_is_selected_by_its_own_path() -> None:
    created = ExistingDirectory.fake()
    assert WorktreePath.of(created).selector() == WorktreeSelector(f"path:{created.root}")


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


def name_of(branch: BranchSlug) -> WorktreeName:
    return WorktreeName.of_branch(branch, IssueIdentifier.fake())


def test_drops_the_git_user_prefix_orca_adds_back() -> None:
    assert name_of(BranchSlug("mab/add-widget")) == WorktreeName("add-widget")


def test_drops_the_issue_identifier_linear_prepends() -> None:
    assert name_of(BranchSlug("mab/e-4289-add-widget")) == WorktreeName("add-widget")


def test_drops_a_slugified_conventional_commit_type() -> None:
    assert name_of(BranchSlug.fake()) == WorktreeName("add-widget")


def test_drops_a_slugified_conventional_commit_scope() -> None:
    assert name_of(BranchSlug("mab/e-4289-fixci-broken-cache")) == WorktreeName("broken-cache")


def test_strips_a_leading_type_like_word_even_when_it_is_not_a_commit_type() -> None:
    assert name_of(BranchSlug("mab/e-4289-feature-flags")) == WorktreeName("flags")


def test_keeps_a_bare_slug_untouched() -> None:
    assert name_of(BranchSlug("mab/add-widget-to-the-thing")) == WorktreeName(
        "add-widget-to-the-thing"
    )


def test_falls_back_to_the_issue_identifier_without_a_branch() -> None:
    assert WorktreeName.of_branch(BranchSlug(""), IssueIdentifier.fake()) == WorktreeName("E-4289")


def test_falls_back_to_a_literal_name_without_a_branch_or_issue() -> None:
    assert WorktreeName.of_branch(BranchSlug(""), None) == WorktreeName("linear-workspace")


def test_moving_a_workspace_names_the_board_column_rather_than_its_id() -> None:
    assert ColumnLabel.fake().assignment(WorktreeSelector.current()).root == (
        "orca",
        "worktree",
        "set",
        "--worktree",
        "current",
        "--workspace-status",
        "Implementing",
        "--json",
    )


def test_asks_which_columns_exist_by_naming_one_that_cannot() -> None:
    assert ColumnLabel.unknown().assignment(WorktreeSelector.current()).root == (
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
    with pytest.raises(OrcaError, match="meant to refuse"):
        _ = envelope.refusal()
