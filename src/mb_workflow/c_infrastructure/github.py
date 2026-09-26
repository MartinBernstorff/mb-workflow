import logging
from itertools import chain
from typing import override

from mb_workflow.b_core.c_secondary_ports.code_review import (
    CodeForge,
    refuse_incomplete,
    refuse_missing,
)
from mb_workflow.b_core.d_domain_model.git import BranchName, BranchNames
from mb_workflow.b_core.d_domain_model.pull_request import (
    CheckoutDirectory,
    MergedSince,
    PrNumber,
    PrTitle,
    PullRequest,
    PullRequests,
    ReviewDecision,
    ReviewRequest,
)
from mb_workflow.c_infrastructure.shell import (
    Command,
    CommandOutput,
    CommandRunner,
    ExistingDirectory,
)
from mb_workflow.d_lib.models import Payload, Value

logger = logging.getLogger(__name__)


class PullRequestPayload(Payload):
    number: PrNumber
    title: PrTitle
    head_ref_name: BranchName

    @staticmethod
    def fake() -> PullRequestPayload:
        return PullRequestPayload(
            number=PrNumber.fake(), title=PrTitle.fake(), head_ref_name=BranchName.fake()
        )

    def pull_request(self) -> PullRequest:
        return PullRequest(number=self.number, title=self.title, branch=self.head_ref_name)


class PullRequestPayloads(Value[tuple[PullRequestPayload, ...]]):
    @staticmethod
    def fake() -> PullRequestPayloads:
        return PullRequestPayloads((PullRequestPayload.fake(),))

    @staticmethod
    def parse(output: CommandOutput) -> PullRequests:
        payloads = PullRequestPayloads.model_validate_json(output.root)
        return PullRequests(tuple(payload.pull_request() for payload in payloads.root))


class SearchQuery(Value[str]):
    @staticmethod
    def fake() -> SearchQuery:
        return SearchQuery.merged_since(MergedSince.fake())

    @staticmethod
    def merged_since(since: MergedSince) -> SearchQuery:
        return SearchQuery(f"merged:>={since.root.isoformat()}")


class ReviewFlag(Value[str]):
    @staticmethod
    def fake() -> ReviewFlag:
        return ReviewFlag.of(ReviewDecision.approve)

    @staticmethod
    def of(decision: ReviewDecision) -> ReviewFlag:
        match decision:
            case ReviewDecision.approve:
                return ReviewFlag("--approve")
            case ReviewDecision.request_changes:
                return ReviewFlag("--request-changes")
            case ReviewDecision.comment:
                return ReviewFlag("--comment")


class ReviewEvent(Value[str]):
    @staticmethod
    def fake() -> ReviewEvent:
        return ReviewEvent.of(ReviewDecision.approve)

    @staticmethod
    def of(decision: ReviewDecision) -> ReviewEvent:
        match decision:
            case ReviewDecision.approve:
                return ReviewEvent("APPROVE")
            case ReviewDecision.request_changes:
                return ReviewEvent("REQUEST_CHANGES")
            case ReviewDecision.comment:
                return ReviewEvent("COMMENT")


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


def review_command(pr: PrNumber, request: ReviewRequest) -> Command:
    review = ("gh", "pr", "review", str(pr.root), ReviewFlag.of(request.decision).root)
    if len(request.body.root) == 0:
        return Command(review)
    return Command((*review, "--body", request.body.root))


def pending_submission(pr: PrNumber, pending: ReviewId, request: ReviewRequest) -> Command:
    submit = (
        "gh",
        "api",
        "--method",
        "POST",
        f"repos/{{owner}}/{{repo}}/pulls/{pr.root}/reviews/{pending.root}/events",
        "--silent",
        "-f",
        f"event={ReviewEvent.of(request.decision).root}",
    )
    if len(request.body.root) == 0:
        return Command(submit)
    return Command((*submit, "-f", f"body={request.body.root}"))


class GitHub(CodeForge):
    def __init__(self, shell: CommandRunner) -> None:
        self._shell = shell
        _ = shell.run(Command(("gh", "--version")))

    @override
    def review_requested(self) -> PullRequests:
        return PullRequestPayloads.parse(
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

    @override
    def merged_branches(self, since: MergedSince) -> BranchNames:
        return PullRequestPayloads.parse(
            self._shell.run(
                Command(
                    (
                        "gh",
                        "pr",
                        "list",
                        "--state",
                        "merged",
                        "--search",
                        SearchQuery.merged_since(since).root,
                        "--limit",
                        "1000",
                        "--json",
                        "number,title,headRefName",
                    )
                )
            )
        ).branches()

    @override
    def checkout(self, pr: PrNumber, into: CheckoutDirectory) -> None:
        refuse_missing(into)
        _ = self._shell.at(ExistingDirectory(into.root)).run(
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

    @override
    def submit(self, pr: PrNumber, request: ReviewRequest) -> None:
        refuse_incomplete(request)
        pending = self.reviews(pr).pending_by(self.viewer())
        if pending is None:
            _ = self._shell.run(review_command(pr, request))
            return
        logger.info("Submitting pending review %s.", pending.root)
        _ = self._shell.run(pending_submission(pr, pending, request))
