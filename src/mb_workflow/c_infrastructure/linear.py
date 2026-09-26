from subprocess import CalledProcessError
from typing import TYPE_CHECKING

from pydantic import AliasPath, Field, ValidationError

from mb_workflow.b_core.c_secondary_ports.issue_tracker import IssueTrackerError
from mb_workflow.b_core.d_domain_model.issue import (
    Issue,
    IssueIdentifier,
    Issues,
    LabelName,
    LabelNames,
    ProjectName,
    StatusName,
)
from mb_workflow.c_infrastructure.shell import Command, CommandOutput
from mb_workflow.d_lib.models import Payload, Value

if TYPE_CHECKING:
    from collections.abc import Callable

    from mb_workflow.b_core.d_domain_model.issue import Assignee, IssueFilter
    from mb_workflow.c_infrastructure.shell import CommandRunner


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


class LabelPayload(Payload):
    name: LabelName

    @staticmethod
    def fake() -> LabelPayload:
        return LabelPayload(name=LabelName.fake())


class LabelPage(Payload):
    nodes: tuple[LabelPayload, ...]
    page_info: PageInfo

    @staticmethod
    def fake() -> LabelPage:
        return LabelPage(nodes=(LabelPayload.fake(),), page_info=PageInfo.fake())

    @staticmethod
    def parse(output: CommandOutput) -> LabelPage:
        return LabelPage.model_validate_json(output.root)

    def names(self) -> LabelNames:
        return LabelNames(tuple(label.name for label in self.nodes))

    def next_cursor(self) -> PageCursor | None:
        return self.page_info.next_cursor()


class ProjectPayload(Payload):
    name: ProjectName

    @staticmethod
    def fake() -> ProjectPayload:
        return ProjectPayload(name=ProjectName.fake())


class IssuePayload(Payload):
    identifier: IssueIdentifier
    status: StatusName = Field(validation_alias=AliasPath("state", "name"))
    project: ProjectPayload | None = None
    labels: tuple[LabelPayload, ...] = Field(
        default=(), validation_alias=AliasPath("labels", "nodes")
    )

    @staticmethod
    def fake() -> IssuePayload:
        return IssuePayload(
            identifier=IssueIdentifier.fake(),
            status=StatusName.fake(),
            project=ProjectPayload.fake(),
            labels=(LabelPayload.fake(),),
        )

    @staticmethod
    def parse(output: CommandOutput) -> IssuePayload:
        return IssuePayload.model_validate_json(output.root)

    def issue(self) -> Issue:
        return Issue(
            identifier=self.identifier,
            status=self.status,
            project=self.project.name if self.project is not None else None,
            labels=LabelNames(tuple(label.name for label in self.labels)),
        )


class IssuePage(Payload):
    nodes: tuple[IssuePayload, ...]
    page_info: PageInfo

    @staticmethod
    def fake() -> IssuePage:
        return IssuePage(nodes=(IssuePayload.fake(),), page_info=PageInfo.fake())

    @staticmethod
    def parse(output: CommandOutput) -> IssuePage:
        return IssuePage.model_validate_json(output.root)

    def issues(self) -> Issues:
        return Issues(tuple(node.issue() for node in self.nodes))

    def next_cursor(self) -> PageCursor | None:
        return self.page_info.next_cursor()


def paged(page: Command, cursor: PageCursor | None) -> Command:
    if cursor is None:
        return page
    return Command((*page.root, "--after", cursor.root))


def label_lookup(cursor: PageCursor | None) -> Command:
    return paged(Command(("linearis", "labels", "list", "--limit", "250")), cursor)


def issue_lookup(wanted: IssueFilter, cursor: PageCursor | None) -> Command:
    page = (
        "linearis",
        "issues",
        "list",
        "--creator",
        wanted.creator.root,
        "--created-after",
        wanted.created_after.root.isoformat(),
        "--limit",
        "250",
    )
    return paged(Command(page), cursor)


def issue_read(issue: IssueIdentifier) -> Command:
    return Command(("linearis", "issues", "read", issue.root))


def label_addition(issue: IssueIdentifier, label: LabelName) -> Command:
    return Command(
        ("linearis", "issues", "update", issue.root, "--labels", label.root, "--label-mode", "add")
    )


def label_overwrite(issue: IssueIdentifier, labels: LabelNames) -> Command:
    update = ("linearis", "issues", "update", issue.root)
    if len(labels.root) == 0:
        return Command((*update, "--clear-labels"))
    return Command(
        (
            *update,
            "--labels",
            ",".join(name.root for name in labels.root),
            "--label-mode",
            "overwrite",
        )
    )


def assignment(issue: IssueIdentifier, assignee: Assignee) -> Command:
    return Command(("linearis", "issues", "update", issue.root, "--assignee", assignee.root))


class Linear:
    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner

    def labels(self) -> LabelNames:
        found: list[LabelName] = []
        cursor: PageCursor | None = None
        while True:
            page = self._parsed(LabelPage.parse, label_lookup(cursor))
            found.extend(page.names().root)
            cursor = page.next_cursor()
            if cursor is None:
                return LabelNames(tuple(found))

    def issues(self, wanted: IssueFilter) -> Issues:
        found: list[Issue] = []
        cursor: PageCursor | None = None
        while True:
            page = self._parsed(IssuePage.parse, issue_lookup(wanted, cursor))
            found.extend(page.issues().root)
            cursor = page.next_cursor()
            if cursor is None:
                return Issues(tuple(found))

    def read(self, issue: IssueIdentifier) -> Issue:
        return self._parsed(IssuePayload.parse, issue_read(issue)).issue()

    def add_label(self, issue: IssueIdentifier, label: LabelName) -> None:
        _ = self._run(label_addition(issue, label))

    # linearis can add or overwrite labels but never remove one, so removal overwrites what is left.
    def set_labels(self, issue: IssueIdentifier, labels: LabelNames) -> None:
        _ = self._run(label_overwrite(issue, labels))

    def assign(self, issue: IssueIdentifier, assignee: Assignee) -> None:
        _ = self._run(assignment(issue, assignee))

    def _run(self, command: Command) -> CommandOutput:
        try:
            return self._runner.run(command)
        except CalledProcessError as error:
            raise IssueTrackerError(f"{error} {error.stderr}".strip()) from error
        except FileNotFoundError as error:
            raise IssueTrackerError(f"{error.filename} is not installed or not on PATH.") from error

    def _parsed[T](self, parse: Callable[[CommandOutput], T], command: Command) -> T:
        output = self._run(command)
        try:
            return parse(output)
        except ValidationError as error:
            raise IssueTrackerError(f"linearis answered in an unexpected shape: {error}") from error
