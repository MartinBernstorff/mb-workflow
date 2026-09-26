from datetime import date, timedelta
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from mb_workflow.b_core.d_domain_model.git import BranchName, BranchNames
from mb_workflow.d_lib.models import Model, Value

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.clock import Today


class PrNumber(Value[int]):
    @staticmethod
    def fake() -> PrNumber:
        return PrNumber(1234)


class PrTitle(Value[str]):
    @staticmethod
    def fake() -> PrTitle:
        return PrTitle("Add review workspaces")


class PullRequest(Model):
    number: PrNumber
    title: PrTitle
    branch: BranchName

    @staticmethod
    def fake() -> PullRequest:
        return PullRequest(number=PrNumber.fake(), title=PrTitle.fake(), branch=BranchName.fake())


class PullRequests(Value[tuple[PullRequest, ...]]):
    @staticmethod
    def fake() -> PullRequests:
        return PullRequests((PullRequest.fake(),))

    def branches(self) -> BranchNames:
        return BranchNames(tuple(pr.branch for pr in self.root))


class Lookback(Value[int]):
    @staticmethod
    def fake() -> Lookback:
        return Lookback(30)


class MergedSince(Value[date]):
    @staticmethod
    def fake() -> MergedSince:
        return MergedSince(date(2026, 8, 9))

    @staticmethod
    def of(lookback: Lookback, today: Today) -> MergedSince:
        return MergedSince(today.root - timedelta(days=lookback.root))


class CheckoutDirectory(Value[Path]):
    @staticmethod
    def fake() -> CheckoutDirectory:
        return CheckoutDirectory(Path("/Users/me/orca/workspaces/mb-workflow/pr-1234"))


class BodyRequired(Value[bool]):
    @staticmethod
    def fake() -> BodyRequired:
        return BodyRequired(False)


class ReviewDecision(StrEnum):
    approve = "approve"
    request_changes = "request-changes"
    comment = "comment"

    def body_required(self) -> BodyRequired:
        return BodyRequired(self != ReviewDecision.approve)


class ReviewBody(Value[str]):
    @staticmethod
    def fake() -> ReviewBody:
        return ReviewBody("Looks good to me.")


class Complete(Value[bool]):
    @staticmethod
    def fake() -> Complete:
        return Complete(True)


class ReviewRequest(Model):
    decision: ReviewDecision
    body: ReviewBody

    @staticmethod
    def fake() -> ReviewRequest:
        return ReviewRequest(decision=ReviewDecision.approve, body=ReviewBody.fake())

    def complete(self) -> Complete:
        return Complete(not self.decision.body_required().root or len(self.body.root) > 0)
