import logging
from itertools import chain
from typing import TYPE_CHECKING

from mb_workflow.b_core.d_domain_model.git import BranchName, BranchNames
from mb_workflow.b_core.d_domain_model.pull_request import (
    MergedSince,
    PrNumber,
    PrTitle,
    PullRequest,
    PullRequests,
)
from mb_workflow.b_core.d_domain_model.review import ReviewDecision, ReviewId, ReviewRequest
from mb_workflow.c_infrastructure.shell import Command, CommandOutput, Shell
from mb_workflow.d_lib.models import Payload, Value

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.directory import ExistingDirectory

logger = logging.getLogger(__name__)


class PullRequestPayload(Payload):
    number: PrNumber
    title: PrTitle
    head_ref_name: BranchName

    @staticmethod
    def fake() -> PullRequestPayload:
        return PullRequestPayload.of(PullRequest.fake())

    @staticmethod
    def of(pr: PullRequest) -> PullRequestPayload:
        return PullRequestPayload(number=pr.number, title=pr.title, head_ref_name=pr.branch)

    def pull_request(self) -> PullRequest:
        return PullRequest(number=self.number, title=self.title, branch=self.head_ref_name)


class PullRequestPayloads(Value[tuple[PullRequestPayload, ...]]):
    @staticmethod
    def fake() -> PullRequestPayloads:
        return PullRequestPayloads((PullRequestPayload.fake(),))


def pull_requests(output: CommandOutput) -> PullRequests:
    payloads = PullRequestPayloads.model_validate_json(output.root)
    return PullRequests(tuple(payload.pull_request() for payload in payloads.root))


class SearchQuery(Value[str]):
    @staticmethod
    def fake() -> SearchQuery:
        return merged_search(MergedSince.fake())


def merged_search(since: MergedSince) -> SearchQuery:
    return SearchQuery(f"merged:>={since.root.isoformat()}")


class ReviewFlag(Value[str]):
    @staticmethod
    def fake() -> ReviewFlag:
        return ReviewFlag("--approve")


class ReviewEvent(Value[str]):
    @staticmethod
    def fake() -> ReviewEvent:
        return ReviewEvent("APPROVE")


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


def flag_of(decision: ReviewDecision) -> ReviewFlag:
    match decision:
        case ReviewDecision.approve:
            return ReviewFlag("--approve")
        case ReviewDecision.reject:
            return ReviewFlag("--request-changes")
        case ReviewDecision.comment:
            return ReviewFlag("--comment")


def event_of(decision: ReviewDecision) -> ReviewEvent:
    match decision:
        case ReviewDecision.approve:
            return ReviewEvent("APPROVE")
        case ReviewDecision.reject:
            return ReviewEvent("REQUEST_CHANGES")
        case ReviewDecision.comment:
            return ReviewEvent("COMMENT")


def review_command(pr: PrNumber, request: ReviewRequest) -> Command:
    review = ("gh", "pr", "review", str(pr.root), flag_of(request.decision).root)
    if len(request.body.root) == 0:
        return Command(review)
    return Command((*review, "--body", request.body.root))


def submission_command(pr: PrNumber, pending: ReviewId, request: ReviewRequest) -> Command:
    submit = (
        "gh",
        "api",
        "--method",
        "POST",
        f"repos/{{owner}}/{{repo}}/pulls/{pr.root}/reviews/{pending.root}/events",
        "--silent",
        "-f",
        f"event={event_of(request.decision).root}",
    )
    if len(request.body.root) == 0:
        return Command(submit)
    return Command((*submit, "-f", f"body={request.body.root}"))


class GitHub:
    def __init__(self, shell: Shell) -> None:
        self._shell = shell
        _ = shell.run(Command(("gh", "--version")))

    def review_requested(self) -> PullRequests:
        return pull_requests(
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
        return pull_requests(
            self._shell.run(
                Command(
                    (
                        "gh",
                        "pr",
                        "list",
                        "--state",
                        "merged",
                        "--search",
                        merged_search(since).root,
                        "--limit",
                        "1000",
                        "--json",
                        "number,title,headRefName",
                    )
                )
            )
        ).branches()

    def checkout(self, pr: PrNumber, into: ExistingDirectory) -> None:
        _ = self._shell.in_directory(into).run(
            Command(("gh", "pr", "checkout", str(pr.root), "--force"))
        )

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

    def submit_review(self, pr: PrNumber, request: ReviewRequest) -> None:
        request.ensure_body()
        pending = self.reviews(pr).pending_by(self.viewer())
        if pending is None:
            _ = self._shell.run(review_command(pr, request))
            return
        logger.info("Submitting pending review %s.", pending.root)
        _ = self._shell.run(submission_command(pr, pending, request))
