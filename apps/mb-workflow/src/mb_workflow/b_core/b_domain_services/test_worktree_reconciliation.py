from pathlib import Path

from assertions import Assert

from mb_workflow.b_core.b_domain_services.worktree_reconciliation import WorktreeReconciliation
from mb_workflow.b_core.d_domain_model.git import BranchName, BranchNames, Ref
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
from mb_workflow.b_core.d_domain_model.pull_request import (
    PrNumber,
    PrNumbers,
    PrTitle,
    PullRequest,
    PullRequests,
)
from mb_workflow.b_core.d_domain_model.workspace import (
    RepoId,
    WorkspaceStatus,
    WorkspaceStatuses,
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


def awaiting_me() -> WorkspaceStatus:
    return WorkspaceStatus("status-reviewing")


def review_statuses() -> WorkspaceStatuses:
    return WorkspaceStatuses((WorkspaceStatus.fake(), awaiting_me()))


def elsewhere() -> WorktreePath:
    return WorktreePath(Path.cwd())


def stale_among(prs: PullRequests, worktrees: Worktrees) -> Worktrees:
    return WorktreeReconciliation.stale(
        prs, worktrees, RepoId.fake(), review_statuses(), elsewhere()
    )


def test_keeps_prs_with_no_workspace() -> None:
    Assert.that(
        WorktreeReconciliation.uncovered(PullRequests.fake(), Worktrees((bare_worktree(),)))
    ).matches(PullRequests.fake())


def test_skips_a_pr_linked_by_issue_number() -> None:
    worktrees = Worktrees((bare_worktree().model_copy(update={"pull_request": PrNumber.fake()}),))
    Assert.that(WorktreeReconciliation.uncovered(PullRequests.fake(), worktrees)).matches(
        PullRequests(())
    )


def test_skips_a_pr_whose_branch_is_already_checked_out() -> None:
    worktrees = Worktrees((bare_worktree().model_copy(update={"branch": Ref.fake()}),))
    Assert.that(WorktreeReconciliation.uncovered(PullRequests.fake(), worktrees)).matches(
        PullRequests(())
    )


def test_a_workspace_for_another_pr_does_not_cover_this_one() -> None:
    prs = PullRequests((PullRequest.fake(), other_pr()))
    worktrees = Worktrees((bare_worktree().model_copy(update={"branch": Ref.fake()}),))
    Assert.that(WorktreeReconciliation.uncovered(prs, worktrees)).matches(
        PullRequests((other_pr(),))
    )


def test_no_prs_yields_nothing_to_do() -> None:
    Assert.that(WorktreeReconciliation.uncovered(PullRequests(()), Worktrees.fake())).matches(
        PullRequests(())
    )


def test_a_review_workspace_survives_while_its_pr_awaits_review() -> None:
    Assert.that(stale_among(PullRequests.fake(), Worktrees((review_worktree(),)))).matches(
        Worktrees(())
    )


def test_a_review_workspace_is_stale_once_its_pr_no_longer_awaits_review() -> None:
    worktrees = Worktrees((review_worktree(),))
    Assert.that(stale_among(PullRequests((other_pr(),)), worktrees)).matches(worktrees)


def test_a_review_workspace_in_another_review_column_also_goes_stale() -> None:
    worktrees = Worktrees((review_worktree().model_copy(update={"status": awaiting_me()}),))
    Assert.that(stale_among(PullRequests((other_pr(),)), worktrees)).matches(worktrees)


def test_a_workspace_linked_to_my_ticket_is_never_stale_in_a_review_column() -> None:
    worktrees = Worktrees((review_worktree().model_copy(update={"issue": IssueIdentifier.fake()}),))
    Assert.that(stale_among(PullRequests((other_pr(),)), worktrees)).matches(Worktrees(()))


def test_a_workspace_outside_the_review_status_is_never_stale() -> None:
    worktrees = Worktrees((review_worktree().model_copy(update={"status": None}),))
    Assert.that(stale_among(PullRequests(()), worktrees)).matches(Worktrees(()))


def test_a_workspace_in_another_repo_is_never_stale() -> None:
    worktrees = Worktrees((review_worktree().model_copy(update={"repo": RepoId("elsewhere")}),))
    Assert.that(stale_among(PullRequests(()), worktrees)).matches(Worktrees(()))


def test_a_workspace_linked_to_no_pull_request_is_never_stale_in_a_review_column() -> None:
    worktrees = Worktrees((review_worktree().model_copy(update={"pull_request": None}),))
    Assert.that(stale_among(PullRequests(()), worktrees)).matches(Worktrees(()))


def test_a_review_workspace_matched_only_by_branch_survives() -> None:
    worktrees = Worktrees(
        (
            review_worktree().model_copy(
                update={"pull_request": other_pr().number, "branch": Ref.fake()}
            ),
        )
    )
    Assert.that(stale_among(PullRequests.fake(), worktrees)).matches(Worktrees(()))


def test_the_workspace_you_are_standing_in_is_never_stale() -> None:
    here = elsewhere()
    worktrees = Worktrees((review_worktree().model_copy(update={"path": here}),))
    Assert.that(
        WorktreeReconciliation.stale(
            PullRequests(()), worktrees, RepoId.fake(), review_statuses(), here
        )
    ).matches(Worktrees(()))


def test_a_workspace_on_a_branch_is_prunable() -> None:
    worktrees = Worktrees((bare_worktree().model_copy(update={"branch": Ref.fake()}),))
    Assert.that(WorktreeReconciliation.prunable(worktrees, RepoId.fake(), elsewhere())).matches(
        worktrees
    )


def test_a_workspace_without_a_branch_is_not_prunable() -> None:
    Assert.that(
        WorktreeReconciliation.prunable(Worktrees((bare_worktree(),)), RepoId.fake(), elsewhere())
    ).matches(Worktrees(()))


def test_a_workspace_in_another_repo_is_not_prunable() -> None:
    worktrees = Worktrees(
        (bare_worktree().model_copy(update={"branch": Ref.fake(), "repo": RepoId("elsewhere")}),)
    )
    Assert.that(WorktreeReconciliation.prunable(worktrees, RepoId.fake(), elsewhere())).matches(
        Worktrees(())
    )


def test_the_workspace_you_are_standing_in_is_not_prunable() -> None:
    here = elsewhere()
    worktrees = Worktrees(
        (bare_worktree().model_copy(update={"branch": Ref.fake(), "path": here}),)
    )
    Assert.that(WorktreeReconciliation.prunable(worktrees, RepoId.fake(), here)).matches(
        Worktrees(())
    )


def test_a_union_keeps_each_workspace_once() -> None:
    Assert.that(WorktreeReconciliation.union(Worktrees.fake(), Worktrees.fake())).matches(
        Worktrees.fake()
    )


def test_a_union_keeps_distinct_workspaces() -> None:
    second = bare_worktree().model_copy(update={"path": WorktreePath(Path("/tmp/other"))})
    Assert.that(WorktreeReconciliation.union(Worktrees.fake(), Worktrees((second,)))).matches(
        Worktrees((Worktree.fake(), second))
    )


def test_selects_the_workspaces_on_the_given_branches() -> None:
    wanted = bare_worktree().model_copy(update={"branch": Ref.fake()})
    other = bare_worktree().model_copy(update={"branch": Ref("refs/heads/feat/other")})
    Assert.that(
        WorktreeReconciliation.on_branches(Worktrees((wanted, other)), BranchNames.fake())
    ).matches(Worktrees((wanted,)))


def obsolete_among(
    prs: PullRequests, merged: BranchNames, worktrees: Worktrees, mine: PrNumbers | None = None
) -> Worktrees:
    return WorktreeReconciliation.obsolete(
        stale=stale_among(prs, worktrees),
        mine=PrNumbers(()) if mine is None else mine,
        merged=merged,
        worktrees=worktrees,
        repo=RepoId.fake(),
        here=elsewhere(),
    )


def test_a_stale_review_workspace_is_obsolete() -> None:
    worktrees = Worktrees((review_worktree(),))
    Assert.that(obsolete_among(PullRequests(()), BranchNames(()), worktrees)).matches(worktrees)


def test_a_workspace_on_a_merged_branch_is_obsolete() -> None:
    worktrees = Worktrees((bare_worktree().model_copy(update={"branch": Ref.fake()}),))
    Assert.that(obsolete_among(PullRequests(()), BranchNames.fake(), worktrees)).matches(worktrees)


def test_a_workspace_on_an_unmerged_branch_outside_review_is_not_obsolete() -> None:
    worktrees = Worktrees((bare_worktree().model_copy(update={"branch": Ref.fake()}),))
    Assert.that(obsolete_among(PullRequests(()), BranchNames(()), worktrees)).matches(Worktrees(()))


def test_a_workspace_both_stale_and_merged_is_obsolete_once() -> None:
    worktrees = Worktrees((review_worktree().model_copy(update={"branch": Ref.fake()}),))
    Assert.that(obsolete_among(PullRequests(()), BranchNames.fake(), worktrees)).matches(worktrees)


def test_a_stale_workspace_for_a_pull_request_i_opened_is_not_obsolete() -> None:
    worktrees = Worktrees((review_worktree(),))
    Assert.that(
        obsolete_among(PullRequests(()), BranchNames(()), worktrees, PrNumbers.fake())
    ).matches(Worktrees(()))


def test_a_worktree_list_names_the_pull_requests_linked_to_it() -> None:
    worktrees = Worktrees((review_worktree(), bare_worktree()))
    Assert.that(worktrees.pull_requests()).matches(PrNumbers.fake())
