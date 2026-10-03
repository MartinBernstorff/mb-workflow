import pytest
from safe_result import Err, Ok

from mb_workflow.b_core.a_features.finalize_review import FinalizeReview, NotFinalizableError
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


def refusal(worktree: Worktree) -> NotFinalizableError:
    match FinalizeReview.reviewed_pr(worktree, WorkspaceStatus.fake()):
        case Err(error):
            return error
        case Ok(pr):
            pytest.fail(f"Expected a refusal, got PR #{pr.root}.")


def test_finalizes_a_worktree_in_the_reviewing_status() -> None:
    reviewed = FinalizeReview.reviewed_pr(Worktree.fake(), WorkspaceStatus.fake())
    assert reviewed == Ok(PrNumber.fake())


def test_rejects_a_worktree_in_another_status() -> None:
    worktree = Worktree.fake().model_copy(update={"status": WorkspaceStatus("in-progress")})
    assert "expected status-8" in str(refusal(worktree))


def test_rejects_a_worktree_without_a_status() -> None:
    worktree = Worktree.fake().model_copy(update={"status": None})
    assert "status none" in str(refusal(worktree))


def test_rejects_a_worktree_with_no_linked_pull_request() -> None:
    worktree = Worktree.fake().model_copy(update={"pull_request": None})
    assert "no linked pull request" in str(refusal(worktree))


def test_submits_the_decision_on_the_linked_pull_request() -> None:
    review = FakeCodeReview(PullRequests.fake())
    finalized = FinalizeReview.finalize(
        review, standing_in(Worktree.fake()), ReviewRequest.fake(), WorkspaceStatus.fake()
    )
    assert finalized == Ok(None)
    assert review.submitted() == (
        SubmittedReview(pr=PrNumber.fake(), request=ReviewRequest.fake(), drafted=Drafted(False)),
    )


def test_removes_the_worktree_once_the_review_is_in() -> None:
    manager = standing_in(Worktree.fake())
    _ = FinalizeReview.finalize(
        FakeCodeReview(PullRequests.fake()), manager, ReviewRequest.fake(), WorkspaceStatus.fake()
    )
    assert manager.worktrees() == Worktrees(())


def test_a_refused_review_keeps_the_worktree() -> None:
    manager = standing_in(Worktree.fake())
    bare = ReviewRequest(decision=ReviewDecision.comment, body=ReviewBody(""))
    with pytest.raises(CodeReviewError, match="comment requires comment text"):
        _ = FinalizeReview.finalize(
            FakeCodeReview(PullRequests.fake()), manager, bare, WorkspaceStatus.fake()
        )
    assert manager.worktrees() == Worktrees.fake()


def test_a_worktree_in_another_status_submits_nothing_and_keeps_the_worktree() -> None:
    review = FakeCodeReview(PullRequests.fake())
    manager = standing_in(Worktree.fake().model_copy(update={"status": None}))
    before = manager.worktrees()
    finalized = FinalizeReview.finalize(
        review, manager, ReviewRequest.fake(), WorkspaceStatus.fake()
    )
    assert isinstance(finalized, Err)
    assert isinstance(finalized.error, NotFinalizableError)
    assert review.submitted() == ()
    assert manager.worktrees() == before
