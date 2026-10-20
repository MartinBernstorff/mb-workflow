from assertions import Assert

from mb_workflow.b_core.d_domain_model.clock import Today
from mb_workflow.b_core.d_domain_model.git import BranchName, BranchNames
from mb_workflow.b_core.d_domain_model.pull_request import (
    CommentBodies,
    CommentBody,
    Complete,
    Lookback,
    MergedSince,
    PrNumber,
    PrTitle,
    PullRequest,
    PullRequests,
    ReviewBody,
    ReviewDecision,
    ReviewRequest,
)


def test_rejecting_and_commenting_need_a_body() -> None:
    Assert.that(ReviewDecision.request_changes.body_required().root).is_true()
    Assert.that(ReviewDecision.comment.body_required().root).is_true()
    Assert.that(ReviewDecision.approve.body_required().root).is_false()


def test_an_approval_without_a_body_is_complete() -> None:
    request = ReviewRequest(decision=ReviewDecision.approve, body=ReviewBody(""))
    Assert.that(request.complete()).matches(Complete(True))


def test_a_comment_without_a_body_is_incomplete() -> None:
    request = ReviewRequest(decision=ReviewDecision.comment, body=ReviewBody(""))
    Assert.that(request.complete()).matches(Complete(False))


def test_a_comment_with_a_body_is_complete() -> None:
    request = ReviewRequest(decision=ReviewDecision.comment, body=ReviewBody("Nit."))
    Assert.that(request.complete()).matches(Complete(True))


def test_collects_the_branch_of_each_pr() -> None:
    other_branch = BranchName("feat/other")
    other = PullRequest(number=PrNumber(7), title=PrTitle("Other work"), branch=other_branch)
    prs = PullRequests((PullRequest.fake(), other))
    Assert.that(prs.branches()).matches(BranchNames((BranchName.fake(), other_branch)))


def test_the_window_starts_the_lookback_before_today() -> None:
    Assert.that(MergedSince.of(Lookback.fake(), Today.fake())).matches(MergedSince.fake())


def test_a_comment_marked_with_a_robot_is_agent_written() -> None:
    Assert.that(CommentBody("🤖 Consider a guard here.").agent_written().root).is_true()


def test_an_unmarked_comment_is_not_agent_written() -> None:
    Assert.that(CommentBody.fake().agent_written().root).is_false()


def test_drops_the_agent_written_comments() -> None:
    comments = CommentBodies((CommentBody("🤖 Consider a guard here."), CommentBody.fake()))
    Assert.that(comments.without_agent_written()).matches(CommentBodies.fake())
