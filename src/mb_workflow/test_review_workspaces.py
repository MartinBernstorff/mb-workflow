from mb_workflow.git import BranchName, Ref
from mb_workflow.github import PrNumber, PrTitle, PullRequest, PullRequests
from mb_workflow.orca import RepoId, Worktree, WorktreePath, Worktrees
from mb_workflow.review_workspaces import uncovered


def other_pr() -> PullRequest:
    return PullRequest(
        number=PrNumber(7), title=PrTitle("Other work"), head_ref_name=BranchName("feat/other")
    )


def bare_worktree() -> Worktree:
    return Worktree(repo_id=RepoId.fake(), path=WorktreePath.fake())


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
