from datetime import UTC, datetime

from mb_workflow.b_core.d_domain_model.claim import (
    ClaimHolder,
    ClaimId,
    CommentBody,
    HostName,
)
from mb_workflow.c_infrastructure.linear_claims import CommentedAt, CommentPayload, CommentThread
from mb_workflow.d_lib.models import Value


class Second(Value[int]):
    @staticmethod
    def fake() -> Second:
        return Second(0)


def comment(claim: ClaimId, body: CommentBody, second: Second) -> CommentPayload:
    return CommentPayload(
        id=claim,
        body=body,
        created_at=CommentedAt(datetime(2026, 9, 26, 12, 0, second.root, tzinfo=UTC)),
    )


def test_claims_are_ordered_by_when_they_were_posted_whatever_order_linear_lists_them() -> None:
    rival = ClaimHolder.fake().model_copy(update={"host": HostName("bob-mbp.local")})
    thread = CommentThread.fake().model_copy(
        update={
            "comments": (
                comment(ClaimId("a"), rival.comment(), Second(1)),
                comment(ClaimId("b"), ClaimHolder.fake().comment(), Second(0)),
            )
        }
    )
    assert thread.claims().ids() == (ClaimId("b"), ClaimId("a"))


def test_claims_posted_in_the_same_millisecond_are_ordered_by_id() -> None:
    thread = CommentThread.fake().model_copy(
        update={
            "comments": (
                comment(ClaimId("b"), ClaimHolder.fake().comment(), Second(0)),
                comment(ClaimId("a"), ClaimHolder.fake().comment(), Second(0)),
            )
        }
    )
    assert thread.claims().ids() == (ClaimId("a"), ClaimId("b"))


def test_comments_that_are_no_claims_are_left_out() -> None:
    thread = CommentThread.fake().model_copy(
        update={
            "comments": (
                comment(ClaimId("a"), CommentBody("Looks good."), Second(0)),
                comment(ClaimId("b"), ClaimHolder.fake().comment(), Second(1)),
            )
        }
    )
    assert thread.claims().ids() == (ClaimId("b"),)
