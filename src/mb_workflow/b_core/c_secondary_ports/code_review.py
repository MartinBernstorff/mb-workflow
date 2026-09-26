from typing import TYPE_CHECKING, Protocol

from mb_workflow.b_core.d_domain_model.directory import ExistingDirectory
from mb_workflow.b_core.d_domain_model.pull_request import PrNumber, PullRequests
from mb_workflow.b_core.d_domain_model.review import PendingReview, ReviewId, ReviewRequest
from mb_workflow.d_lib.models import Model, Value

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.git import BranchNames
    from mb_workflow.b_core.d_domain_model.pull_request import MergedSince


class CodeReview(Protocol):
    def review_requested(self) -> PullRequests: ...

    def merged_branches(self, since: MergedSince) -> BranchNames: ...

    def checkout(self, pr: PrNumber, into: ExistingDirectory) -> None: ...

    def submit_review(self, pr: PrNumber, request: ReviewRequest) -> None: ...


class Submission(Model):
    pr: PrNumber
    request: ReviewRequest
    pending: ReviewId | None

    @staticmethod
    def fake() -> Submission:
        return Submission(pr=PrNumber.fake(), request=ReviewRequest.fake(), pending=None)


class Submissions(Value[tuple[Submission, ...]]):
    @staticmethod
    def fake() -> Submissions:
        return Submissions((Submission.fake(),))


class Checkout(Model):
    pr: PrNumber
    into: ExistingDirectory

    @staticmethod
    def fake() -> Checkout:
        return Checkout(pr=PrNumber.fake(), into=ExistingDirectory.fake())


class Checkouts(Value[tuple[Checkout, ...]]):
    @staticmethod
    def fake() -> Checkouts:
        return Checkouts((Checkout.fake(),))


class FakeCodeReview:
    def __init__(
        self,
        requested: PullRequests | None = None,
        merged: PullRequests | None = None,
        pending: PendingReview | None = None,
    ) -> None:
        self._requested = requested if requested is not None else PullRequests(())
        self._merged = merged if merged is not None else PullRequests(())
        self._pending = pending
        self._submitted = Submissions(())
        self._checked_out = Checkouts(())

    def review_requested(self) -> PullRequests:
        return self._requested

    def merged_branches(self, since: MergedSince) -> BranchNames:
        _ = since
        return self._merged.branches()

    def checkout(self, pr: PrNumber, into: ExistingDirectory) -> None:
        self._checked_out = Checkouts((*self._checked_out.root, Checkout(pr=pr, into=into)))

    def submit_review(self, pr: PrNumber, request: ReviewRequest) -> None:
        request.ensure_body()
        pending = self._pending.id if self._pending is not None and self._pending.pr == pr else None
        if pending is not None:
            self._pending = None
        self._submitted = Submissions(
            (*self._submitted.root, Submission(pr=pr, request=request, pending=pending))
        )

    def submitted(self) -> Submissions:
        return self._submitted

    def checked_out(self) -> Checkouts:
        return self._checked_out
