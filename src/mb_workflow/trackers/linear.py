import logging
from datetime import date, timedelta
from enum import StrEnum
from subprocess import CalledProcessError
from typing import TYPE_CHECKING

from pydantic import AliasPath, Field, ValidationError

from mb_workflow.issue import IssueIdentifier
from mb_workflow.models import Model, Payload, Value
from mb_workflow.shell import Command, CommandOutput, Shell

if TYPE_CHECKING:
    from mb_workflow.clock import Today

logger = logging.getLogger(__name__)


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


class PageCursor(Value[str]):
    @staticmethod
    def fake() -> PageCursor:
        return PageCursor("17bec4c8-ce66-4546-a54f-aaefbc27e32f")


class MorePages(Value[bool]):
    @staticmethod
    def fake() -> MorePages:
        return MorePages(True)


class PageInfo(Payload):
    has_next_page: MorePages
    end_cursor: PageCursor | None = None

    @staticmethod
    def fake() -> PageInfo:
        return PageInfo(has_next_page=MorePages.fake(), end_cursor=PageCursor.fake())

    # linearis reports an end cursor on the last page too, so only the flag ends the walk.
    def next_cursor(self) -> PageCursor | None:
        return self.end_cursor if self.has_next_page.root else None


class LabelKnown(Value[bool]):
    @staticmethod
    def fake() -> LabelKnown:
        return LabelKnown(True)


class LabelPage(Payload):
    nodes: tuple[Label, ...]
    page_info: PageInfo

    @staticmethod
    def fake() -> LabelPage:
        return LabelPage(nodes=(Label.fake(),), page_info=PageInfo.fake())

    @staticmethod
    def parse(output: CommandOutput) -> LabelPage:
        return LabelPage.model_validate_json(output.root)

    def names(self) -> LabelNames:
        return LabelNames(tuple(label.name for label in self.nodes))

    def next_cursor(self) -> PageCursor | None:
        return self.page_info.next_cursor()


class LabelNames(Value[tuple[LabelName, ...]]):
    @staticmethod
    def fake() -> LabelNames:
        return LabelNames((LabelName.fake(),))

    @staticmethod
    def lookup(cursor: PageCursor | None) -> Command:
        page = ("linearis", "labels", "list", "--limit", "250")
        if cursor is None:
            return Command(page)
        return Command((*page, "--after", cursor.root))

    def has(self, label: LabelName) -> LabelKnown:
        return LabelKnown(label in self.root)

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


class LabelledIssue(Payload):
    labels: tuple[Label, ...] = Field(default=(), validation_alias=AliasPath("labels", "nodes"))

    def label_names(self) -> LabelNames:
        return LabelNames(tuple(label.name for label in self.labels))


class Issue(LabelledIssue):
    identifier: IssueIdentifier
    state: IssueState = Field(validation_alias=AliasPath("state", "name"))

    @staticmethod
    def fake() -> Issue:
        return Issue(
            identifier=IssueIdentifier.fake(), state=IssueState.todo, labels=(Label.fake(),)
        )

    @staticmethod
    def parse(output: CommandOutput) -> Issue:
        return Issue.model_validate_json(output.root)


# ProjectName and StatusName share a base so one exclusion pattern can match either.
class IssueText(Value[str]): ...


class ProjectName(IssueText):
    @staticmethod
    def fake() -> ProjectName:
        return ProjectName("BE: Campaigns MVP")


class Project(Payload):
    name: ProjectName

    @staticmethod
    def fake() -> Project:
        return Project(name=ProjectName.fake())


class StatusName(IssueText):
    @staticmethod
    def fake() -> StatusName:
        return StatusName("Todo")


class ListedIssue(LabelledIssue):
    identifier: IssueIdentifier
    status: StatusName = Field(validation_alias=AliasPath("state", "name"))
    project: Project | None = None

    @staticmethod
    def fake() -> ListedIssue:
        return ListedIssue(
            identifier=IssueIdentifier.fake(),
            status=StatusName.fake(),
            project=Project.fake(),
            labels=(),
        )


class ListedIssues(Value[tuple[ListedIssue, ...]]):
    @staticmethod
    def fake() -> ListedIssues:
        return ListedIssues((ListedIssue.fake(),))


class IssuePage(Payload):
    nodes: tuple[ListedIssue, ...]
    page_info: PageInfo

    @staticmethod
    def fake() -> IssuePage:
        return IssuePage(nodes=(ListedIssue.fake(),), page_info=PageInfo.fake())

    @staticmethod
    def parse(output: CommandOutput) -> IssuePage:
        return IssuePage.model_validate_json(output.root)

    def issues(self) -> ListedIssues:
        return ListedIssues(self.nodes)

    def next_cursor(self) -> PageCursor | None:
        return self.page_info.next_cursor()


class Creator(Value[str]):
    @staticmethod
    def fake() -> Creator:
        return Creator("mab@flowbase.io")


class CreatedWithin(Value[int]):
    @staticmethod
    def fake() -> CreatedWithin:
        return CreatedWithin(30)


class CreatedAfter(Value[date]):
    @staticmethod
    def fake() -> CreatedAfter:
        return CreatedAfter(date(2026, 8, 9))

    @staticmethod
    def of(window: CreatedWithin, today: Today) -> CreatedAfter:
        return CreatedAfter(today.root - timedelta(days=window.root))


class IssueQuery(Model):
    creator: Creator
    created_after: CreatedAfter

    @staticmethod
    def fake() -> IssueQuery:
        return IssueQuery(creator=Creator.fake(), created_after=CreatedAfter.fake())

    def command(self, cursor: PageCursor | None) -> Command:
        page = (
            "linearis",
            "issues",
            "list",
            "--creator",
            self.creator.root,
            "--created-after",
            self.created_after.root.isoformat(),
            "--limit",
            "250",
        )
        if cursor is None:
            return Command(page)
        return Command((*page, "--after", cursor.root))


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

    def workspace_labels(self) -> LabelNames:
        found: list[LabelName] = []
        cursor: PageCursor | None = None
        while True:
            page = LabelPage.parse(self._shell.run(LabelNames.lookup(cursor)))
            found.extend(page.names().root)
            cursor = page.next_cursor()
            if cursor is None:
                return LabelNames(tuple(found))

    def issues(self, query: IssueQuery) -> ListedIssues:
        found: list[ListedIssue] = []
        cursor: PageCursor | None = None
        while True:
            page = IssuePage.parse(self._shell.run(query.command(cursor)))
            found.extend(page.issues().root)
            cursor = page.next_cursor()
            if cursor is None:
                return ListedIssues(tuple(found))

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
