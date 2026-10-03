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


def test_reads_the_pull_request_of_a_worktree_in_the_reviewing_status() -> None:
    reviewed = FinalizeReview.reviewed_pr(Worktree.fake(), WorkspaceStatus.fake())
    assert reviewed == Ok(PrNumber.fake())


@pytest.mark.parametrize(
    ("update", "reason"),
    [
        ({"status": WorkspaceStatus("in-progress")}, "expected status-8"),
        ({"status": None}, "status none"),
        ({"pull_request": None}, "no linked pull request"),
    ],
)
def test_an_unfinalizable_worktree_is_refused_and_left_alone(
    update: dict[str, object], reason: str
) -> None:
    review = FakeCodeReview(PullRequests.fake())
    manager = standing_in(Worktree.fake().model_copy(update=update))
    before = manager.worktrees()
    finalized = FinalizeReview.finalize(
        review, manager, ReviewRequest.fake(), WorkspaceStatus.fake()
    )
    assert isinstance(finalized, Err)
    assert isinstance(finalized.error, NotFinalizableError)
    assert reason in str(finalized.error)
    assert review.submitted() == ()
    assert manager.worktrees() == before


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
    finalized = FinalizeReview.finalize(
        FakeCodeReview(PullRequests.fake()), manager, ReviewRequest.fake(), WorkspaceStatus.fake()
    )
    assert finalized == Ok(None)
    assert manager.worktrees() == Worktrees(())


def test_a_refused_review_keeps_the_worktree() -> None:
    manager = standing_in(Worktree.fake())
    bare = ReviewRequest(decision=ReviewDecision.comment, body=ReviewBody(""))
    reason = "comment requires comment text"
    finalized = FinalizeReview.finalize(
        FakeCodeReview(PullRequests.fake()), manager, bare, WorkspaceStatus.fake()
    )
    assert isinstance(finalized, Err)
    assert isinstance(finalized.error, CodeReviewError)
    assert reason in str(finalized.error)
    assert manager.worktrees() == Worktrees.fake()
