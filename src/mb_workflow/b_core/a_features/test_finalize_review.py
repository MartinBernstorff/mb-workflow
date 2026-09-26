import pytest

from mb_workflow.b_core.a_features.finalize_review import (
    NotFinalizableError,
    reviewed_pr,
    submit_linked_review,
)
from mb_workflow.b_core.c_secondary_ports.code_review import FakeCodeReview, Submissions
from mb_workflow.b_core.d_domain_model.pull_request import PrNumber
from mb_workflow.b_core.d_domain_model.review import ReviewDecision, ReviewRequest
from mb_workflow.c_infrastructure.orca import WorkspaceStatus, Worktree


def test_finalizes_a_worktree_in_the_reviewing_status() -> None:
    assert reviewed_pr(Worktree.fake(), WorkspaceStatus.fake()) == PrNumber.fake()


def test_rejects_a_worktree_in_another_status() -> None:
    worktree = Worktree.fake().model_copy(
        update={"workspace_status": WorkspaceStatus("in-progress")}
    )
    with pytest.raises(NotFinalizableError, match="expected status-8"):
        _ = reviewed_pr(worktree, WorkspaceStatus.fake())


def test_rejects_a_worktree_without_a_status() -> None:
    worktree = Worktree.fake().model_copy(update={"workspace_status": None})
    with pytest.raises(NotFinalizableError, match="status none"):
        _ = reviewed_pr(worktree, WorkspaceStatus.fake())


def test_rejects_a_worktree_with_no_linked_pull_request() -> None:
    worktree = Worktree.fake().model_copy(update={"linked_issue": None})
    with pytest.raises(NotFinalizableError, match="no linked pull request"):
        _ = reviewed_pr(worktree, WorkspaceStatus.fake())


def test_submits_the_review_on_the_linked_pull_request() -> None:
    code_review = FakeCodeReview()
    submit_linked_review(code_review, Worktree.fake(), ReviewRequest.fake(), WorkspaceStatus.fake())
    assert code_review.submitted() == Submissions.fake()


def test_submits_nothing_for_a_worktree_in_another_status() -> None:
    code_review = FakeCodeReview()
    worktree = Worktree.fake().model_copy(update={"workspace_status": None})
    with pytest.raises(NotFinalizableError):
        submit_linked_review(code_review, worktree, ReviewRequest.fake(), WorkspaceStatus.fake())
    assert code_review.submitted() == Submissions(())


def test_rejecting_and_commenting_need_a_body() -> None:
    assert ReviewDecision.reject.body_required().root
    assert ReviewDecision.comment.body_required().root
    assert not ReviewDecision.approve.body_required().root
