import logging

from mb_workflow.git import BranchName
from mb_workflow.models import Model, Payload, Value
from mb_workflow.shell import Command, CommandOutput, ExistingDirectory, Shell

logger = logging.getLogger(__name__)


class PrNumber(Value[int]):
    @staticmethod
    def fake() -> PrNumber:
        return PrNumber(1234)


class PrTitle(Value[str]):
    @staticmethod
    def fake() -> PrTitle:
        return PrTitle("Add review workspaces")


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


class ReviewBody(Value[str]):
    @staticmethod
    def fake() -> ReviewBody:
        return ReviewBody("Looks good to me.")


class ReviewFlag(Value[str]):
    @staticmethod
    def fake() -> ReviewFlag:
        return ReviewFlag("--approve")


class BodyRequired(Value[bool]):
    @staticmethod
    def fake() -> BodyRequired:
        return BodyRequired(False)


class ReviewDecision(Model):
    flag: ReviewFlag
    body_required: BodyRequired

    @staticmethod
    def fake() -> ReviewDecision:
        return ReviewDecision.approve()

    @staticmethod
    def approve() -> ReviewDecision:
        return ReviewDecision(flag=ReviewFlag("--approve"), body_required=BodyRequired(False))

    @staticmethod
    def reject() -> ReviewDecision:
        return ReviewDecision(
            flag=ReviewFlag("--request-changes"), body_required=BodyRequired(True)
        )

    @staticmethod
    def comment() -> ReviewDecision:
        return ReviewDecision(flag=ReviewFlag("--comment"), body_required=BodyRequired(True))


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

    def checkout(self, pr: PrNumber, into: ExistingDirectory) -> None:
        _ = Shell(into).run(Command(("gh", "pr", "checkout", str(pr.root), "--force")))

    def review(self, pr: PrNumber, request: ReviewRequest) -> None:
        _ = self._shell.run(request.command(pr))
