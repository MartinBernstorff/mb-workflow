import pytest

from mb_workflow.b_core.a_features.finalize_review import (
    NotFinalizableError,
    finalize,
    reviewed_pr,
)
from mb_workflow.b_core.c_secondary_ports.code_review import (
    CodeReviewError,
    Drafted,
    FakeCodeReview,
    SubmittedReview,
)
from mb_workflow.b_core.c_secondary_ports.workspace_manager import FakeWorkspaceManager
from mb_workflow.b_core.d_domain_model.pull_request import (
    PrNumber,
    PullRequests,
    ReviewBody,
    ReviewDecision,
    ReviewRequest,
)
from mb_workflow.b_core.d_domain_model.workspace import (
    WorkspaceStatus,
    Worktree,
    WorktreePath,
    Worktrees,
)


def standing_in(worktree: Worktree) -> FakeWorkspaceManager:
    return FakeWorkspaceManager(Worktrees((worktree,)), WorktreePath.fake())


def test_finalizes_a_worktree_in_the_reviewing_status() -> None:
    assert reviewed_pr(Worktree.fake(), WorkspaceStatus.fake()) == PrNumber.fake()


def test_rejects_a_worktree_in_another_status() -> None:
    worktree = Worktree.fake().model_copy(update={"status": WorkspaceStatus("in-progress")})
    with pytest.raises(NotFinalizableError, match="expected status-8"):
        _ = reviewed_pr(worktree, WorkspaceStatus.fake())


def test_rejects_a_worktree_without_a_status() -> None:
    worktree = Worktree.fake().model_copy(update={"status": None})
    with pytest.raises(NotFinalizableError, match="status none"):
        _ = reviewed_pr(worktree, WorkspaceStatus.fake())


def test_rejects_a_worktree_with_no_linked_pull_request() -> None:
    worktree = Worktree.fake().model_copy(update={"pull_request": None})
    with pytest.raises(NotFinalizableError, match="no linked pull request"):
        _ = reviewed_pr(worktree, WorkspaceStatus.fake())


def test_submits_the_decision_on_the_linked_pull_request() -> None:
    review = FakeCodeReview(PullRequests.fake())
    finalize(review, standing_in(Worktree.fake()), ReviewRequest.fake(), WorkspaceStatus.fake())
    assert review.submitted() == (
        SubmittedReview(pr=PrNumber.fake(), request=ReviewRequest.fake(), drafted=Drafted(False)),
    )


def test_removes_the_worktree_once_the_review_is_in() -> None:
    manager = standing_in(Worktree.fake())
    finalize(
        FakeCodeReview(PullRequests.fake()), manager, ReviewRequest.fake(), WorkspaceStatus.fake()
    )
    assert manager.worktrees() == Worktrees(())


def test_a_refused_review_keeps_the_worktree() -> None:
    manager = standing_in(Worktree.fake())
    bare = ReviewRequest(decision=ReviewDecision.comment, body=ReviewBody(""))
    with pytest.raises(CodeReviewError, match="comment requires comment text"):
        finalize(FakeCodeReview(PullRequests.fake()), manager, bare, WorkspaceStatus.fake())
    assert manager.worktrees() == Worktrees.fake()


def test_a_worktree_in_another_status_submits_nothing() -> None:
    review = FakeCodeReview(PullRequests.fake())
    elsewhere = Worktree.fake().model_copy(update={"status": None})
    with pytest.raises(NotFinalizableError):
        finalize(review, standing_in(elsewhere), ReviewRequest.fake(), WorkspaceStatus.fake())
    assert review.submitted() == ()
