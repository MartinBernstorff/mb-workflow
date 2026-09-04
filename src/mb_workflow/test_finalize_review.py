import pytest

from mb_workflow.finalize_review import NotFinalizableError, reviewed_pr
from mb_workflow.github import PrNumber, ReviewBody, ReviewDecision, ReviewRequest
from mb_workflow.orca import WorkspaceStatus, Worktree


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


def test_approval_carries_its_comment() -> None:
    assert ReviewRequest.fake().command(PrNumber.fake()).root == (
        ("gh", "pr", "review", "1234", "--approve", "--body", "Looks good to me.")
    )


def test_an_empty_comment_is_left_off_the_command() -> None:
    request = ReviewRequest(decision=ReviewDecision.approve(), body=ReviewBody(""))
    assert request.command(PrNumber.fake()).root == ("gh", "pr", "review", "1234", "--approve")


def test_rejecting_and_commenting_need_a_body() -> None:
    assert ReviewDecision.reject().body_required.root
    assert ReviewDecision.comment().body_required.root
    assert not ReviewDecision.approve().body_required.root
