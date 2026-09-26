from enum import StrEnum

from mb_workflow.b_core.d_domain_model.pull_request import PrNumber
from mb_workflow.d_lib.models import Model, Value


class MissingReviewBodyError(Exception):
    pass


class BodyRequired(Value[bool]):
    @staticmethod
    def fake() -> BodyRequired:
        return BodyRequired(False)


class ReviewDecision(StrEnum):
    approve = "approve"
    reject = "reject"
    comment = "comment"

    @staticmethod
    def fake() -> ReviewDecision:
        return ReviewDecision.approve

    def body_required(self) -> BodyRequired:
        return BodyRequired(self is not ReviewDecision.approve)


class ReviewBody(Value[str]):
    @staticmethod
    def fake() -> ReviewBody:
        return ReviewBody("Looks good to me.")


class ReviewRequest(Model):
    decision: ReviewDecision
    body: ReviewBody

    @staticmethod
    def fake() -> ReviewRequest:
        return ReviewRequest(decision=ReviewDecision.fake(), body=ReviewBody.fake())

    def ensure_body(self) -> None:
        if self.decision.body_required().root and len(self.body.root) == 0:
            raise MissingReviewBodyError(f"{self.decision} requires comment text")


class ReviewId(Value[int]):
    @staticmethod
    def fake() -> ReviewId:
        return ReviewId(5678)


class PendingReview(Model):
    pr: PrNumber
    id: ReviewId

    @staticmethod
    def fake() -> PendingReview:
        return PendingReview(pr=PrNumber.fake(), id=ReviewId.fake())
