import logging

from mb_workflow.git import BranchName
from mb_workflow.models import Payload, Value
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


class GitHub:
    def __init__(self, shell: Shell) -> None:
        self._shell = shell

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
