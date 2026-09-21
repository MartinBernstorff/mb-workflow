import logging
from datetime import date, timedelta
from itertools import chain
from typing import TYPE_CHECKING

from mb_workflow.b_core.git import BranchName, BranchNames
from mb_workflow.b_core.pull_request import PrNumber, PrTitle
from mb_workflow.c_infrastructure.shell import Command, CommandOutput, ExistingDirectory, Shell
from mb_workflow.d_lib.models import Model, Payload, Value

if TYPE_CHECKING:
    from mb_workflow.b_core.clock import Today

logger = logging.getLogger(__name__)


class PullRequest(Payload):
    number: PrNumber
    title: PrTitle
    head_ref_name: BranchName

    @staticmethod
    def fake() -> PullRequest:
        return PullRequest(
            number=PrNumber.fake(), title=PrTitle.fake(), head_ref_name=BranchName.fake()
        )


class PullRequests(Value[tuple[PullRequest, ...]]):
    @staticmethod
    def fake() -> PullRequests:
        return PullRequests((PullRequest.fake(),))

    @staticmethod
    def parse(output: CommandOutput) -> PullRequests:
        return PullRequests.model_validate_json(output.root)

    def head_refs(self) -> BranchNames:
        return BranchNames(tuple(pr.head_ref_name for pr in self.root))


class SearchQuery(Value[str]):
    @staticmethod
    def fake() -> SearchQuery:
        return MergedSince.fake().search()


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

    def search(self) -> SearchQuery:
        return SearchQuery(f"merged:>={self.root.isoformat()}")


class ReviewBody(Value[str]):
    @staticmethod
    def fake() -> ReviewBody:
        return ReviewBody("Looks good to me.")


class ReviewFlag(Value[str]):
    @staticmethod
    def fake() -> ReviewFlag:
        return ReviewFlag("--approve")


class ReviewEvent(Value[str]):
    @staticmethod
    def fake() -> ReviewEvent:
        return ReviewEvent("APPROVE")


class ReviewId(Value[int]):
    @staticmethod
    def fake() -> ReviewId:
        return ReviewId(5678)


class ReviewState(Value[str]):
    @staticmethod
    def fake() -> ReviewState:
        return ReviewState.pending()

    @staticmethod
    def pending() -> ReviewState:
        return ReviewState("PENDING")


class UserLogin(Value[str]):
    @staticmethod
    def fake() -> UserLogin:
        return UserLogin("MartinBernstorff")

    @staticmethod
    def parse(output: CommandOutput) -> UserLogin:
        return UserLogin(output.root.strip())


class ReviewAuthor(Payload):
    login: UserLogin

    @staticmethod
    def fake() -> ReviewAuthor:
        return ReviewAuthor(login=UserLogin.fake())


class Review(Payload):
    id: ReviewId
    state: ReviewState
    user: ReviewAuthor

    @staticmethod
    def fake() -> Review:
        return Review(id=ReviewId.fake(), state=ReviewState.fake(), user=ReviewAuthor.fake())


class ReviewPages(Value[tuple[tuple[Review, ...], ...]]):
    @staticmethod
    def fake() -> ReviewPages:
        return ReviewPages(((Review.fake(),),))


class Reviews(Value[tuple[Review, ...]]):
    @staticmethod
    def fake() -> Reviews:
        return Reviews((Review.fake(),))

    @staticmethod
    def parse(output: CommandOutput) -> Reviews:
        pages = ReviewPages.model_validate_json(output.root)
        return Reviews(tuple(chain.from_iterable(pages.root)))

    def pending_by(self, author: UserLogin) -> ReviewId | None:
        mine = [
            review.id
            for review in self.root
            if review.state == ReviewState.pending() and review.user.login == author
        ]
        return mine[-1] if len(mine) > 0 else None


class BodyRequired(Value[bool]):
    @staticmethod
    def fake() -> BodyRequired:
        return BodyRequired(False)


class ReviewDecision(Model):
    flag: ReviewFlag
    event: ReviewEvent
    body_required: BodyRequired

    @staticmethod
    def fake() -> ReviewDecision:
        return ReviewDecision.approve()

    @staticmethod
    def approve() -> ReviewDecision:
        return ReviewDecision(
            flag=ReviewFlag("--approve"),
            event=ReviewEvent("APPROVE"),
            body_required=BodyRequired(False),
        )

    @staticmethod
    def reject() -> ReviewDecision:
        return ReviewDecision(
            flag=ReviewFlag("--request-changes"),
            event=ReviewEvent("REQUEST_CHANGES"),
            body_required=BodyRequired(True),
        )

    @staticmethod
    def comment() -> ReviewDecision:
        return ReviewDecision(
            flag=ReviewFlag("--comment"),
            event=ReviewEvent("COMMENT"),
            body_required=BodyRequired(True),
        )


class ReviewRequest(Model):
    decision: ReviewDecision
    body: ReviewBody

    @staticmethod
    def fake() -> ReviewRequest:
        return ReviewRequest(decision=ReviewDecision.fake(), body=ReviewBody.fake())

    def command(self, pr: PrNumber) -> Command:
        review = ("gh", "pr", "review", str(pr.root), self.decision.flag.root)
        if len(self.body.root) == 0:
            return Command(review)
        return Command((*review, "--body", self.body.root))

    def submission(self, pr: PrNumber, pending: ReviewId) -> Command:
        submit = (
            "gh",
            "api",
            "--method",
            "POST",
            f"repos/{{owner}}/{{repo}}/pulls/{pr.root}/reviews/{pending.root}/events",
            "--silent",
            "-f",
            f"event={self.decision.event.root}",
        )
        if len(self.body.root) == 0:
            return Command(submit)
        return Command((*submit, "-f", f"body={self.body.root}"))


class GitHub:
    def __init__(self, shell: Shell) -> None:
        self._shell = shell
        _ = shell.run(Command(("gh", "--version")))

    def review_requested(self) -> PullRequests:
        return PullRequests.parse(
            self._shell.run(
                Command(
                    (
                        "gh",
                        "pr",
                        "list",
                        "--search",
                        "is:open review-requested:@me",
                        "--json",
                        "number,title,headRefName",
                    )
                )
            )
        )

    def merged_branches(self, since: MergedSince) -> BranchNames:
        return PullRequests.parse(
            self._shell.run(
                Command(
                    (
                        "gh",
                        "pr",
                        "list",
                        "--state",
                        "merged",
                        "--search",
                        since.search().root,
                        "--limit",
                        "1000",
                        "--json",
                        "number,title,headRefName",
                    )
                )
            )
        ).head_refs()

    def checkout(self, pr: PrNumber, into: ExistingDirectory) -> None:
        _ = Shell(into).run(Command(("gh", "pr", "checkout", str(pr.root), "--force")))

    def viewer(self) -> UserLogin:
        return UserLogin.parse(self._shell.run(Command(("gh", "api", "user", "--jq", ".login"))))

    def reviews(self, pr: PrNumber) -> Reviews:
        return Reviews.parse(
            self._shell.run(
                Command(
                    (
                        "gh",
                        "api",
                        "--paginate",
                        "--slurp",
                        f"repos/{{owner}}/{{repo}}/pulls/{pr.root}/reviews",
                    )
                )
            )
        )

    def review(self, pr: PrNumber, request: ReviewRequest) -> None:
        pending = self.reviews(pr).pending_by(self.viewer())
        if pending is None:
            _ = self._shell.run(request.command(pr))
            return
        logger.info("Submitting pending review %s.", pending.root)
        _ = self._shell.run(request.submission(pr, pending))
