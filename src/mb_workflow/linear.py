import logging
from enum import StrEnum
from subprocess import CalledProcessError

from pydantic import AliasPath, Field, ValidationError

from mb_workflow.models import Payload, Value
from mb_workflow.shell import Command, CommandOutput, Shell

logger = logging.getLogger(__name__)


class IssueIdentifier(Value[str]):
    @staticmethod
    def fake() -> IssueIdentifier:
        return IssueIdentifier("E-4289")


class BranchSlug(Value[str]):
    @staticmethod
    def fake() -> BranchSlug:
        return BranchSlug(f"mab/{IssueIdentifier.fake().root.lower()}-feat-add-widget")


class Assignee(Value[str]):
    @staticmethod
    def fake() -> Assignee:
        return Assignee("mab@flowbase.io")


class AssignmentFailure(Value[str]):
    @staticmethod
    def fake() -> AssignmentFailure:
        return AssignmentFailure("linearis is not installed or not on PATH")


class IssueState(StrEnum):
    backlog = "Backlog"
    maturing = "Maturing"
    todo = "Todo"
    in_progress = "In Progress"
    in_review = "In Review"
    ready_for_release = "Ready For Release"
    done = "Done"
    canceled = "Canceled"
    duplicate = "Duplicate"
    triage = "Triage"


class Issue(Payload):
    identifier: IssueIdentifier
    state: IssueState = Field(validation_alias=AliasPath("state", "name"))

    @staticmethod
    def fake() -> Issue:
        return Issue(identifier=IssueIdentifier.fake(), state=IssueState.todo)

    @staticmethod
    def parse(output: CommandOutput) -> Issue:
        return Issue.model_validate_json(output.root)


class Linear:
    def __init__(self, shell: Shell) -> None:
        self._shell = shell

    def assign(self, issue: IssueIdentifier, assignee: Assignee) -> AssignmentFailure | None:
        try:
            _ = self._shell.run(
                Command(("linearis", "issues", "update", issue.root, "--assignee", assignee.root))
            )
        except (CalledProcessError, FileNotFoundError) as error:
            return AssignmentFailure(str(error))
        return None

    def state(self, issue: IssueIdentifier) -> IssueState | None:
        try:
            return Issue.parse(
                self._shell.run(Command(("linearis", "issues", "read", issue.root)))
            ).state
        except (CalledProcessError, FileNotFoundError, ValidationError) as error:
            logger.warning("Could not read the state of %s: %s", issue.root, error)
            return None
