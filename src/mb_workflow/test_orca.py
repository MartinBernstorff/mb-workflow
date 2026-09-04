import pytest

from mb_workflow.git import BranchName, Ref
from mb_workflow.github import PrNumber
from mb_workflow.orca import (
    OrcaError,
    RepoId,
    WorktreeComment,
    WorktreeName,
    WorktreePath,
    Worktrees,
    acknowledged,
    created_path,
)
from mb_workflow.shell import CommandOutput, ExistingDirectory


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


def test_worktree_without_branch_or_issue_parses() -> None:
    output = CommandOutput(
        '{"ok":true,"result":{"worktrees":[{"repoId":"r","path":"/tmp/x",'
        '"branch":null,"linkedIssue":null}]}}'
    )
    parsed = Worktrees.parse(output).root[0]
    assert parsed.branch is None
    assert parsed.linked_issue is None


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


def test_acknowledges_a_set_call() -> None:
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


def test_worktree_name_and_comment_describe_the_pr() -> None:
    assert WorktreeName.of(PrNumber.fake()) == WorktreeName.fake()
    assert WorktreeComment.fake().root == "PR #1234 — Add review workspaces"


def test_ref_none_is_not_confused_with_the_default_branch() -> None:
    assert Ref("refs/heads/main").branch() == BranchName("main")
