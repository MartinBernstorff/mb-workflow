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


class LabelName(Value[str]):
    @staticmethod
    def fake() -> LabelName:
        return LabelName("d-implement")

    def addition(self, issue: IssueIdentifier) -> Command:
        return Command(
            (
                "linearis",
                "issues",
                "update",
                issue.root,
                "--labels",
                self.root,
                "--label-mode",
                "add",
            )
        )


class Label(Payload):
    name: LabelName

    @staticmethod
    def fake() -> Label:
        return Label(name=LabelName.fake())


class LabelNames(Value[tuple[LabelName, ...]]):
    @staticmethod
    def fake() -> LabelNames:
        return LabelNames((LabelName.fake(),))

    def without(self, label: LabelName) -> LabelNames:
        return LabelNames(tuple(name for name in self.root if name != label))

    def overwrite(self, issue: IssueIdentifier) -> Command:
        update = ("linearis", "issues", "update", issue.root)
        if len(self.root) == 0:
            return Command((*update, "--clear-labels"))
        return Command(
            (
                *update,
                "--labels",
                ",".join(name.root for name in self.root),
                "--label-mode",
                "overwrite",
            )
        )


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
    labels: tuple[Label, ...] = Field(default=(), validation_alias=AliasPath("labels", "nodes"))

    @staticmethod
    def fake() -> Issue:
        return Issue(
            identifier=IssueIdentifier.fake(), state=IssueState.todo, labels=(Label.fake(),)
        )

    @staticmethod
    def parse(output: CommandOutput) -> Issue:
        return Issue.model_validate_json(output.root)

    def label_names(self) -> LabelNames:
        return LabelNames(tuple(label.name for label in self.labels))


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

    def labels(self, issue: IssueIdentifier) -> LabelNames:
        return self.read(issue).label_names()

    def add_label(self, issue: IssueIdentifier, label: LabelName) -> None:
        _ = self._shell.run(label.addition(issue))

    # linearis can add or overwrite labels but never remove one, so removal overwrites what is left.
    def set_labels(self, issue: IssueIdentifier, labels: LabelNames) -> None:
        _ = self._shell.run(labels.overwrite(issue))

    def read(self, issue: IssueIdentifier) -> Issue:
        return Issue.parse(self._shell.run(Command(("linearis", "issues", "read", issue.root))))

    def state(self, issue: IssueIdentifier) -> IssueState | None:
        try:
            return self.read(issue).state
        except (CalledProcessError, FileNotFoundError, ValidationError) as error:
            logger.warning("Could not read the state of %s: %s", issue.root, error)
            return None
