from datetime import date
from typing import Protocol, override

from safe_result import Err, Ok, Result

from mb_workflow.b_core.d_domain_model.git import BranchNames
from mb_workflow.b_core.d_domain_model.pull_request import (
    CheckoutDirectory,
    CommentBodies,
    MergedSince,
    PrNumber,
    PrNumbers,
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

    # Completes my draft review if there is one, dropping its agent-written comments first.
    def submit(self, pr: PrNumber, request: ReviewRequest) -> Result[None, CodeReviewError]: ...

    # Those of the given pull requests that I opened myself.
    def authored_by_me(self, prs: PrNumbers) -> Result[PrNumbers, CodeReviewError]: ...


class CodeReviewRefusal:
    @staticmethod
    def check_complete(request: ReviewRequest) -> Result[None, CodeReviewError]:
        if not request.complete().root:
            return Err(CodeReviewError(f"{request.decision.value} requires comment text"))
        return Ok(None)

    @staticmethod
    def check_directory(into: CheckoutDirectory) -> Result[None, CodeReviewError]:
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


# My review on a pull request, started on GitHub but not yet submitted.
class DraftReview(Model):
    pr: PrNumber
    comments: CommentBodies

    @staticmethod
    def fake() -> DraftReview:
        return DraftReview(pr=PrNumber.fake(), comments=CommentBodies.fake())


class SubmittedReview(Model):
    pr: PrNumber
    request: ReviewRequest
    drafted: Drafted
    comments: CommentBodies

    @staticmethod
    def fake() -> SubmittedReview:
        return SubmittedReview(
            pr=PrNumber.fake(),
            request=ReviewRequest.fake(),
            drafted=Drafted.fake(),
            comments=CommentBodies(()),
        )


class FakeCodeReview(CodeForge):
    def __init__(
        self,
        requested: PullRequests,
        merged: tuple[MergedPullRequest, ...] = (),
        pending: tuple[DraftReview, ...] = (),
        mine: tuple[PrNumber, ...] = (),
    ) -> None:
        self._requested = requested
        self._merged = merged
        self._pending = {draft.pr: draft.comments for draft in pending}
        self._mine = mine
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
        match CodeReviewRefusal.check_directory(into):
            case Ok():
                self._checkouts[into] = pr
                return Ok(None)
            case Err() as refused:
                return refused

    @override
    def submit(self, pr: PrNumber, request: ReviewRequest) -> Result[None, CodeReviewError]:
        match CodeReviewRefusal.check_complete(request):
            case Ok():
                drafted = Drafted(pr in self._pending)
                comments = self._pending.pop(pr, CommentBodies(())).without_agent_written()
                self._submitted.append(
                    SubmittedReview(pr=pr, request=request, drafted=drafted, comments=comments)
                )
                return Ok(None)
            case Err() as refused:
                return refused

    @override
    def authored_by_me(self, prs: PrNumbers) -> Result[PrNumbers, CodeReviewError]:
        return Ok(PrNumbers(tuple(pr for pr in prs.root if pr in self._mine)))

    def submitted(self) -> tuple[SubmittedReview, ...]:
        return tuple(self._submitted)

    def checked_out(self, into: CheckoutDirectory) -> PrNumber | None:
        return self._checkouts.get(into)


class UnreachableCodeReview(CodeForge):
    def __init__(self) -> None:
        self._unreachable = CodeReviewError("The code review is unreachable.")

    @override
    def review_requested(self) -> Result[PullRequests, CodeReviewError]:
        return Err(self._unreachable)

    @override
    def merged_branches(self, since: MergedSince) -> Result[BranchNames, CodeReviewError]:
        return Err(self._unreachable)

    @override
    def checkout(self, pr: PrNumber, into: CheckoutDirectory) -> Result[None, CodeReviewError]:
        return Err(self._unreachable)

    @override
    def submit(self, pr: PrNumber, request: ReviewRequest) -> Result[None, CodeReviewError]:
        return Err(self._unreachable)

    @override
    def authored_by_me(self, prs: PrNumbers) -> Result[PrNumbers, CodeReviewError]:
        return Err(self._unreachable)
