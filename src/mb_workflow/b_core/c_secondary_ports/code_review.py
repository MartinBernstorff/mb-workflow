from datetime import date
from typing import Protocol, override

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


class CodeReview(Protocol):
    def review_requested(self) -> PullRequests: ...

    def merged_branches(self, since: MergedSince) -> BranchNames: ...

    def checkout(self, pr: PrNumber, into: CheckoutDirectory) -> None: ...

    def submit(self, pr: PrNumber, request: ReviewRequest) -> None: ...


def refuse_incomplete(request: ReviewRequest) -> None:
    if not request.complete().root:
        raise CodeReviewError(f"{request.decision.value} requires comment text")


def refuse_missing(into: CheckoutDirectory) -> None:
    if not into.root.is_dir():
        raise CodeReviewError(f"Cannot check out into {into.root}: not a directory")


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


class FakeCodeReview(CodeReview):
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
    def review_requested(self) -> PullRequests:
        return self._requested

    @override
    def merged_branches(self, since: MergedSince) -> BranchNames:
        return BranchNames(
            tuple(
                merged.pull_request.branch
                for merged in self._merged
                if merged.merged_on.root >= since.root
            )
        )

    @override
    def checkout(self, pr: PrNumber, into: CheckoutDirectory) -> None:
        refuse_missing(into)
        self._checkouts[into] = pr

    @override
    def submit(self, pr: PrNumber, request: ReviewRequest) -> None:
        refuse_incomplete(request)
        drafted = Drafted(pr in self._pending)
        self._pending.discard(pr)
        self._submitted.append(SubmittedReview(pr=pr, request=request, drafted=drafted))

    def submitted(self) -> tuple[SubmittedReview, ...]:
        return tuple(self._submitted)

    def checked_out(self, into: CheckoutDirectory) -> PrNumber | None:
        return self._checkouts.get(into)
