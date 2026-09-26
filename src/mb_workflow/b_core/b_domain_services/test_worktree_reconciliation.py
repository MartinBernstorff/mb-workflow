from pathlib import Path

from mb_workflow.b_core.b_domain_services.worktree_reconciliation import (
    obsolete,
    on_branches,
    prunable,
    stale,
    uncovered,
    union,
)
from mb_workflow.b_core.d_domain_model.clock import Today
from mb_workflow.b_core.d_domain_model.git import BranchName, BranchNames, Ref
from mb_workflow.b_core.d_domain_model.pull_request import (
    Lookback,
    MergedSince,
    PrNumber,
    PrTitle,
    PullRequest,
    PullRequests,
)
from mb_workflow.b_core.d_domain_model.workspace import (
    RepoId,
    WorkspaceStatus,
    Worktree,
    WorktreePath,
    Worktrees,
)


def other_pr() -> PullRequest:
    return PullRequest(
        number=PrNumber(7), title=PrTitle("Other work"), branch=BranchName("feat/other")
    )


def bare_worktree() -> Worktree:
    return Worktree.bare(RepoId.fake(), WorktreePath.fake())


def review_worktree() -> Worktree:
    return bare_worktree().model_copy(
        update={"pull_request": PrNumber.fake(), "status": WorkspaceStatus.fake()}
    )


def elsewhere() -> WorktreePath:
    return WorktreePath(Path.cwd())


def stale_among(prs: PullRequests, worktrees: Worktrees) -> Worktrees:
    return stale(prs, worktrees, RepoId.fake(), WorkspaceStatus.fake(), elsewhere())


def test_keeps_prs_with_no_workspace() -> None:
    assert uncovered(PullRequests.fake(), Worktrees((bare_worktree(),))) == PullRequests.fake()


def test_skips_a_pr_linked_by_issue_number() -> None:
    worktrees = Worktrees((bare_worktree().model_copy(update={"pull_request": PrNumber.fake()}),))
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
    worktrees = Worktrees((review_worktree().model_copy(update={"status": None}),))
    assert stale_among(PullRequests(()), worktrees) == Worktrees(())


def test_a_workspace_in_another_repo_is_never_stale() -> None:
    worktrees = Worktrees((review_worktree().model_copy(update={"repo": RepoId("elsewhere")}),))
    assert stale_among(PullRequests(()), worktrees) == Worktrees(())


def test_a_review_workspace_matched_only_by_branch_survives() -> None:
    worktrees = Worktrees(
        (review_worktree().model_copy(update={"pull_request": None, "branch": Ref.fake()}),)
    )
    assert stale_among(PullRequests.fake(), worktrees) == Worktrees(())


def test_the_workspace_you_are_standing_in_is_never_stale() -> None:
    here = elsewhere()
    worktrees = Worktrees((review_worktree().model_copy(update={"path": here}),))
    assert stale(
        PullRequests(()), worktrees, RepoId.fake(), WorkspaceStatus.fake(), here
    ) == Worktrees(())


def test_a_workspace_on_a_branch_is_prunable() -> None:
    worktrees = Worktrees((bare_worktree().model_copy(update={"branch": Ref.fake()}),))
    assert prunable(worktrees, RepoId.fake(), elsewhere()) == worktrees


def test_a_workspace_without_a_branch_is_not_prunable() -> None:
    assert prunable(Worktrees((bare_worktree(),)), RepoId.fake(), elsewhere()) == Worktrees(())


def test_a_workspace_in_another_repo_is_not_prunable() -> None:
    worktrees = Worktrees(
        (bare_worktree().model_copy(update={"branch": Ref.fake(), "repo": RepoId("elsewhere")}),)
    )
    assert prunable(worktrees, RepoId.fake(), elsewhere()) == Worktrees(())


def test_the_workspace_you_are_standing_in_is_not_prunable() -> None:
    here = elsewhere()
    worktrees = Worktrees(
        (bare_worktree().model_copy(update={"branch": Ref.fake(), "path": here}),)
    )
    assert prunable(worktrees, RepoId.fake(), here) == Worktrees(())


def test_a_union_keeps_each_workspace_once() -> None:
    assert union(Worktrees.fake(), Worktrees.fake()) == Worktrees.fake()


def test_a_union_keeps_distinct_workspaces() -> None:
    second = bare_worktree().model_copy(update={"path": WorktreePath(Path("/tmp/other"))})
    assert union(Worktrees.fake(), Worktrees((second,))) == Worktrees((Worktree.fake(), second))


def test_collects_the_branch_of_each_pr() -> None:
    prs = PullRequests((PullRequest.fake(), other_pr()))
    assert prs.branches() == BranchNames((BranchName.fake(), BranchName("feat/other")))


def test_selects_the_workspaces_on_the_given_branches() -> None:
    wanted = bare_worktree().model_copy(update={"branch": Ref.fake()})
    other = bare_worktree().model_copy(update={"branch": Ref("refs/heads/feat/other")})
    assert on_branches(Worktrees((wanted, other)), BranchNames.fake()) == Worktrees((wanted,))


def test_the_window_starts_the_lookback_before_today() -> None:
    assert MergedSince.of(Lookback.fake(), Today.fake()) == MergedSince.fake()


def obsolete_among(prs: PullRequests, merged: BranchNames, worktrees: Worktrees) -> Worktrees:
    return obsolete(
        requested=prs,
        merged=merged,
        worktrees=worktrees,
        repo=RepoId.fake(),
        status=WorkspaceStatus.fake(),
        here=elsewhere(),
    )


def test_a_stale_review_workspace_is_obsolete() -> None:
    worktrees = Worktrees((review_worktree(),))
    assert obsolete_among(PullRequests(()), BranchNames(()), worktrees) == worktrees


def test_a_workspace_on_a_merged_branch_is_obsolete() -> None:
    worktrees = Worktrees((bare_worktree().model_copy(update={"branch": Ref.fake()}),))
    assert obsolete_among(PullRequests(()), BranchNames.fake(), worktrees) == worktrees


def test_a_workspace_on_an_unmerged_branch_outside_review_is_not_obsolete() -> None:
    worktrees = Worktrees((bare_worktree().model_copy(update={"branch": Ref.fake()}),))
    assert obsolete_among(PullRequests(()), BranchNames(()), worktrees) == Worktrees(())


def test_a_workspace_both_stale_and_merged_is_obsolete_once() -> None:
    worktrees = Worktrees((review_worktree().model_copy(update={"branch": Ref.fake()}),))
    assert obsolete_among(PullRequests(()), BranchNames.fake(), worktrees) == worktrees
