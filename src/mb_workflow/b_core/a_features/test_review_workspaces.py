import logging
from pathlib import Path
from typing import TYPE_CHECKING

from mb_workflow.a_presentation.console import ExitCode
from mb_workflow.b_core.a_features.review_workspaces import (
    Failure,
    Outcome,
    Unchanged,
    on_branches,
    prunable,
    stale,
    uncovered,
    union,
)
from mb_workflow.b_core.d_domain_model.clock import Today
from mb_workflow.b_core.d_domain_model.git import BranchName, BranchNames, Ref
from mb_workflow.b_core.d_domain_model.pull_request import PrNumber, PrTitle
from mb_workflow.c_infrastructure.github import (
    Lookback,
    MergedSince,
    PullRequest,
    PullRequests,
)
from mb_workflow.c_infrastructure.orca import (
    RepoId,
    WorkspaceStatus,
    Worktree,
    WorktreeName,
    WorktreePath,
    Worktrees,
)
from mb_workflow.c_infrastructure.shell import ExistingDirectory

if TYPE_CHECKING:
    import pytest


def other_pr() -> PullRequest:
    return PullRequest(
        number=PrNumber(7), title=PrTitle("Other work"), head_ref_name=BranchName("feat/other")
    )


def bare_worktree() -> Worktree:
    return Worktree(repo_id=RepoId.fake(), path=WorktreePath.fake())


def review_worktree() -> Worktree:
    return bare_worktree().model_copy(
        update={"linked_issue": PrNumber.fake(), "workspace_status": WorkspaceStatus.fake()}
    )


def elsewhere() -> ExistingDirectory:
    return ExistingDirectory(Path.cwd())


def stale_among(prs: PullRequests, worktrees: Worktrees) -> Worktrees:
    return stale(prs, worktrees, RepoId.fake(), WorkspaceStatus.fake(), elsewhere())


def test_keeps_prs_with_no_workspace() -> None:
    assert uncovered(PullRequests.fake(), Worktrees((bare_worktree(),))) == PullRequests.fake()


def test_skips_a_pr_linked_by_issue_number() -> None:
    worktrees = Worktrees((bare_worktree().model_copy(update={"linked_issue": PrNumber.fake()}),))
    assert uncovered(PullRequests.fake(), worktrees) == PullRequests(())


def test_skips_a_pr_whose_branch_is_already_checked_out() -> None:
    worktrees = Worktrees((bare_worktree().model_copy(update={"branch": Ref.fake()}),))
    assert uncovered(PullRequests.fake(), worktrees) == PullRequests(())


def test_a_workspace_for_another_pr_does_not_cover_this_one() -> None:
    prs = PullRequests((PullRequest.fake(), other_pr()))
    worktrees = Worktrees((bare_worktree().model_copy(update={"branch": Ref.fake()}),))
    assert uncovered(prs, worktrees) == PullRequests((other_pr(),))


def test_no_prs_yields_nothing_to_do() -> None:
    assert uncovered(PullRequests(()), Worktrees.fake()) == PullRequests(())


def test_a_review_workspace_survives_while_its_pr_awaits_review() -> None:
    assert stale_among(PullRequests.fake(), Worktrees((review_worktree(),))) == Worktrees(())


def test_a_review_workspace_is_stale_once_its_pr_no_longer_awaits_review() -> None:
    worktrees = Worktrees((review_worktree(),))
    assert stale_among(PullRequests((other_pr(),)), worktrees) == worktrees


def test_a_workspace_outside_the_review_status_is_never_stale() -> None:
    worktrees = Worktrees((review_worktree().model_copy(update={"workspace_status": None}),))
    assert stale_among(PullRequests(()), worktrees) == Worktrees(())


def test_a_workspace_in_another_repo_is_never_stale() -> None:
    worktrees = Worktrees((review_worktree().model_copy(update={"repo_id": RepoId("elsewhere")}),))
    assert stale_among(PullRequests(()), worktrees) == Worktrees(())


def test_a_review_workspace_matched_only_by_branch_survives() -> None:
    worktrees = Worktrees(
        (review_worktree().model_copy(update={"linked_issue": None, "branch": Ref.fake()}),)
    )
    assert stale_among(PullRequests.fake(), worktrees) == Worktrees(())


def test_the_workspace_you_are_standing_in_is_never_stale() -> None:
    here = ExistingDirectory(Path.cwd())
    worktrees = Worktrees((review_worktree().model_copy(update={"path": WorktreePath(here.root)}),))
    assert stale(
        PullRequests(()), worktrees, RepoId.fake(), WorkspaceStatus.fake(), here
    ) == Worktrees(())


def test_a_run_that_touched_nothing_is_unchanged() -> None:
    assert Outcome(created=(), removed=(), failed=()).unchanged() == Unchanged(True)


def test_a_run_that_created_a_workspace_is_not_unchanged() -> None:
    assert Outcome.fake().unchanged() == Unchanged(False)


def test_a_clean_run_exits_zero() -> None:
    assert Outcome.fake().exit_code() == ExitCode(0)


def test_any_failure_exits_non_zero() -> None:
    assert Outcome(created=(), removed=(), failed=(Failure.fake(),)).exit_code() == ExitCode(1)


def test_reports_each_created_workspace(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        Outcome.fake().report()
    assert "Created 1 workspace:" in caplog.text
    assert f"    {WorktreeName.fake().root} \u2192 " in caplog.text


def test_reports_each_removed_workspace(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        Outcome(created=(), removed=(WorktreePath.fake(),), failed=()).report()
    assert "Removed 1 workspace:" in caplog.text
    assert f"    {WorktreePath.fake().root}" in caplog.text


def test_reports_nothing_when_nothing_changed(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        Outcome(created=(), removed=(), failed=()).report()
    assert caplog.text == ""


def test_a_workspace_on_a_branch_is_prunable() -> None:
    worktrees = Worktrees((bare_worktree().model_copy(update={"branch": Ref.fake()}),))
    assert prunable(worktrees, RepoId.fake(), elsewhere()) == worktrees


def test_a_workspace_without_a_branch_is_not_prunable() -> None:
    assert prunable(Worktrees((bare_worktree(),)), RepoId.fake(), elsewhere()) == Worktrees(())


def test_a_workspace_in_another_repo_is_not_prunable() -> None:
    worktrees = Worktrees(
        (bare_worktree().model_copy(update={"branch": Ref.fake(), "repo_id": RepoId("elsewhere")}),)
    )
    assert prunable(worktrees, RepoId.fake(), elsewhere()) == Worktrees(())


def test_the_workspace_you_are_standing_in_is_not_prunable() -> None:
    here = elsewhere()
    worktrees = Worktrees(
        (
            bare_worktree().model_copy(
                update={"branch": Ref.fake(), "path": WorktreePath(here.root)}
            ),
        )
    )
    assert prunable(worktrees, RepoId.fake(), here) == Worktrees(())


def test_a_union_keeps_each_workspace_once() -> None:
    assert union(Worktrees.fake(), Worktrees.fake()) == Worktrees.fake()


def test_a_union_keeps_distinct_workspaces() -> None:
    second = bare_worktree().model_copy(update={"path": WorktreePath(Path("/tmp/other"))})
    assert union(Worktrees.fake(), Worktrees((second,))) == Worktrees((Worktree.fake(), second))


def test_collects_the_head_ref_of_each_pr() -> None:
    prs = PullRequests((PullRequest.fake(), other_pr()))
    assert prs.head_refs() == BranchNames((BranchName.fake(), BranchName("feat/other")))


def test_selects_the_workspaces_on_the_given_branches() -> None:
    wanted = bare_worktree().model_copy(update={"branch": Ref.fake()})
    other = bare_worktree().model_copy(update={"branch": Ref("refs/heads/feat/other")})
    assert on_branches(Worktrees((wanted, other)), BranchNames.fake()) == Worktrees((wanted,))


def test_the_window_starts_the_lookback_before_today() -> None:
    assert MergedSince.of(Lookback.fake(), Today.fake()) == MergedSince.fake()


def test_the_window_searches_for_prs_merged_since_then() -> None:
    assert MergedSince.fake().search().root == "merged:>=2026-08-09"
