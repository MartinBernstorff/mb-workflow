from mb_workflow.b_core.d_domain_model.pull_request import (
    Complete,
    ReviewBody,
    ReviewDecision,
    ReviewRequest,
)


def test_rejecting_and_commenting_need_a_body() -> None:
    assert ReviewDecision.request_changes.body_required().root
    assert ReviewDecision.comment.body_required().root
    assert not ReviewDecision.approve.body_required().root


def test_an_approval_without_a_body_is_complete() -> None:
    request = ReviewRequest(decision=ReviewDecision.approve, body=ReviewBody(""))
    assert request.complete() == Complete(True)


def test_a_comment_without_a_body_is_incomplete() -> None:
    request = ReviewRequest(decision=ReviewDecision.comment, body=ReviewBody(""))
    assert request.complete() == Complete(False)


def test_a_comment_with_a_body_is_complete() -> None:
    request = ReviewRequest(decision=ReviewDecision.comment, body=ReviewBody("Nit."))
    assert request.complete() == Complete(True)
