from datetime import date, timedelta
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
