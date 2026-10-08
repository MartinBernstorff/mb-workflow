import pytest
from safe_result import Err, Ok

from mb_workflow.b_core.a_features.finalize_review import FinalizeReview, NotFinalizableError
from mb_workflow.b_core.c_secondary_ports.code_review import (
    CodeReviewError,
    Drafted,
    FakeCodeReview,
    SubmittedReview,
)
from mb_workflow.b_core.c_secondary_ports.status import FakeStatusStore, UnreachableStatusStore
from mb_workflow.b_core.c_secondary_ports.workspace_manager import (
    FakeWorkspaceManager,
    WorkspaceManagerError,
)
from mb_workflow.b_core.d_domain_model.flow import StateName
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


def board() -> FakeStatusStore:
    return FakeStatusStore(StateName.fake())


def column_of(state: StateName) -> WorkspaceStatus:
    return board().status_for(state).unwrap()


def awaiting_me() -> Worktree:
    return Worktree.fake().model_copy(update={"status": column_of(StateName("reviewing"))})


def standing_in(worktree: Worktree) -> FakeWorkspaceManager:
    return FakeWorkspaceManager(Worktrees((worktree,)), WorktreePath.fake())


def test_reads_the_pull_request_of_a_worktree_in_the_reviewing_status() -> None:
    reviewed = FinalizeReview.reviewed_pr(awaiting_me(), column_of(StateName("reviewing")))
    assert reviewed == Ok(PrNumber.fake())


@pytest.mark.parametrize(
    ("update", "reason"),
    [
        (
            {"status": column_of(StateName("agent-reviewing"))},
            f"expected {column_of(StateName('reviewing')).root}",
        ),
        (
            {"status": WorkspaceStatus("in-progress")},
            f"expected {column_of(StateName('reviewing')).root}",
        ),
        ({"status": None}, "status none"),
        ({"pull_request": None}, "no linked pull request"),
    ],
)
def test_an_unfinalizable_worktree_is_refused_and_left_alone(
    update: dict[str, object], reason: str
) -> None:
    review = FakeCodeReview(PullRequests.fake())
    manager = standing_in(awaiting_me().model_copy(update=update))
    before = manager.worktrees().unwrap()
    finalized = FinalizeReview.finalize(review, manager, board(), ReviewRequest.fake())
    assert isinstance(finalized, Err)
    assert isinstance(finalized.error, NotFinalizableError)
    assert reason in str(finalized.error)
    assert review.submitted() == ()
    assert manager.worktrees().unwrap() == before


def test_submits_the_decision_on_the_linked_pull_request() -> None:
    review = FakeCodeReview(PullRequests.fake())
    finalized = FinalizeReview.finalize(
        review, standing_in(awaiting_me()), board(), ReviewRequest.fake()
    )
    assert finalized == Ok(None)
    assert review.submitted() == (
        SubmittedReview(pr=PrNumber.fake(), request=ReviewRequest.fake(), drafted=Drafted(False)),
    )


def test_removes_the_worktree_once_the_review_is_in() -> None:
    manager = standing_in(awaiting_me())
    finalized = FinalizeReview.finalize(
        FakeCodeReview(PullRequests.fake()), manager, board(), ReviewRequest.fake()
    )
    assert finalized == Ok(None)
    assert manager.worktrees().unwrap() == Worktrees(())


def test_a_refused_review_keeps_the_worktree() -> None:
    manager = standing_in(awaiting_me())
    bare = ReviewRequest(decision=ReviewDecision.comment, body=ReviewBody(""))
    reason = "comment requires comment text"
    finalized = FinalizeReview.finalize(FakeCodeReview(PullRequests.fake()), manager, board(), bare)
    assert isinstance(finalized, Err)
    assert isinstance(finalized.error, CodeReviewError)
    assert reason in str(finalized.error)
    assert manager.worktrees().unwrap() == Worktrees((awaiting_me(),))


def test_an_unreachable_board_submits_no_review_and_keeps_the_worktree() -> None:
    review = FakeCodeReview(PullRequests.fake())
    manager = standing_in(awaiting_me())
    finalized = FinalizeReview.finalize(
        review, manager, UnreachableStatusStore(), ReviewRequest.fake()
    )
    assert isinstance(finalized, Err)
    assert isinstance(finalized.error, WorkspaceManagerError)
    assert review.submitted() == ()
    assert manager.worktrees().unwrap() == Worktrees((awaiting_me(),))


def test_an_unlisted_current_worktree_submits_no_review() -> None:
    review = FakeCodeReview(PullRequests.fake())
    finalized = FinalizeReview.finalize(
        review, standing_in_nothing(), board(), ReviewRequest.fake()
    )
    assert isinstance(finalized, Err)
    assert isinstance(finalized.error, WorkspaceManagerError)
    assert review.submitted() == ()


def standing_in_nothing() -> FakeWorkspaceManager:
    return FakeWorkspaceManager(Worktrees(()), WorktreePath.fake())
