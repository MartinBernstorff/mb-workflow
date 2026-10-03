from datetime import date
from typing import Protocol, override

from safe_result import Err, Ok, Result

from mb_workflow.b_core.d_domain_model.git import BranchNames
from mb_workflow.b_core.d_domain_model.pull_request import (
    CheckoutDirectory,
    MergedSince,
    PrNumber,
    PullRequest,
    PullRequests,
    ReviewRequest,
)
from mb_workflow.d_lib.models import Model, Value


class CodeReviewError(Exception):
    pass


class CodeForge(Protocol):
    def review_requested(self) -> Result[PullRequests, CodeReviewError]: ...

    def merged_branches(self, since: MergedSince) -> Result[BranchNames, CodeReviewError]: ...

    def checkout(self, pr: PrNumber, into: CheckoutDirectory) -> Result[None, CodeReviewError]: ...

    def submit(self, pr: PrNumber, request: ReviewRequest) -> Result[None, CodeReviewError]: ...


def refuse_incomplete(request: ReviewRequest) -> Result[None, CodeReviewError]:
    if not request.complete().root:
        return Err(CodeReviewError(f"{request.decision.value} requires comment text"))
    return Ok(None)


def refuse_missing(into: CheckoutDirectory) -> Result[None, CodeReviewError]:
    if not into.root.is_dir():
        return Err(CodeReviewError(f"Cannot check out into {into.root}: not a directory"))
    return Ok(None)


class MergedOn(Value[date]):
    @staticmethod
    def fake() -> MergedOn:
        return MergedOn(date(2026, 8, 9))


class MergedPullRequest(Model):
    pull_request: PullRequest
    merged_on: MergedOn

    @staticmethod
    def fake() -> MergedPullRequest:
        return MergedPullRequest(pull_request=PullRequest.fake(), merged_on=MergedOn.fake())


class Drafted(Value[bool]):
    @staticmethod
    def fake() -> Drafted:
        return Drafted(False)


class SubmittedReview(Model):
    pr: PrNumber
    request: ReviewRequest
    drafted: Drafted

    @staticmethod
    def fake() -> SubmittedReview:
        return SubmittedReview(
            pr=PrNumber.fake(), request=ReviewRequest.fake(), drafted=Drafted.fake()
        )


class FakeCodeReview(CodeForge):
    def __init__(
        self,
        requested: PullRequests,
        merged: tuple[MergedPullRequest, ...] = (),
        pending: tuple[PrNumber, ...] = (),
    ) -> None:
        self._requested = requested
        self._merged = merged
        self._pending = set(pending)
        self._submitted: list[SubmittedReview] = []
        self._checkouts: dict[CheckoutDirectory, PrNumber] = {}

    @override
    def review_requested(self) -> Result[PullRequests, CodeReviewError]:
        return Ok(self._requested)

    @override
    def merged_branches(self, since: MergedSince) -> Result[BranchNames, CodeReviewError]:
        return Ok(
            BranchNames(
                tuple(
                    merged.pull_request.branch
                    for merged in self._merged
                    if merged.merged_on.root >= since.root
                )
            )
        )

    @override
    def checkout(self, pr: PrNumber, into: CheckoutDirectory) -> Result[None, CodeReviewError]:
        match refuse_missing(into):
            case Ok():
                self._checkouts[into] = pr
                return Ok(None)
            case Err() as refused:
                return refused

    @override
    def submit(self, pr: PrNumber, request: ReviewRequest) -> Result[None, CodeReviewError]:
        match refuse_incomplete(request):
            case Ok():
                drafted = Drafted(pr in self._pending)
                self._pending.discard(pr)
                self._submitted.append(SubmittedReview(pr=pr, request=request, drafted=drafted))
                return Ok(None)
            case Err() as refused:
                return refused

    def submitted(self) -> tuple[SubmittedReview, ...]:
        return tuple(self._submitted)

    def checked_out(self, into: CheckoutDirectory) -> PrNumber | None:
        return self._checkouts.get(into)


class UnreachableCodeReview(CodeForge):
    @override
    def review_requested(self) -> Result[PullRequests, CodeReviewError]:
        return Err(CodeReviewError("The code review is unreachable."))

    @override
    def merged_branches(self, since: MergedSince) -> Result[BranchNames, CodeReviewError]:
        return Err(CodeReviewError("The code review is unreachable."))

    @override
    def checkout(self, pr: PrNumber, into: CheckoutDirectory) -> Result[None, CodeReviewError]:
        return Err(CodeReviewError("The code review is unreachable."))

    @override
    def submit(self, pr: PrNumber, request: ReviewRequest) -> Result[None, CodeReviewError]:
        return Err(CodeReviewError("The code review is unreachable."))
