from subprocess import CalledProcessError
from typing import TYPE_CHECKING, override

from pydantic import AliasPath, Field, ValidationError

from mb_workflow.b_core.c_secondary_ports.issue_tracker import IssueTracker, IssueTrackerError
from mb_workflow.b_core.d_domain_model.issue import (
    Assigned,
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


# Only whether someone is assigned matters, so none of the assignee's fields are read.
class AssigneePayload(Payload):
    @staticmethod
    def fake() -> AssigneePayload:
        return AssigneePayload()


class IssuePayload(Payload):
    identifier: IssueIdentifier
    status: StatusName = Field(validation_alias=AliasPath("state", "name"))
    project: ProjectPayload | None = None
    labels: tuple[LabelPayload, ...] = Field(
        default=(), validation_alias=AliasPath("labels", "nodes")
    )
    assignee: AssigneePayload | None = None

    @staticmethod
    def fake() -> IssuePayload:
        return IssuePayload(
            identifier=IssueIdentifier.fake(),
            status=StatusName.fake(),
            project=ProjectPayload.fake(),
            labels=(LabelPayload.fake(),),
            assignee=AssigneePayload.fake(),
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
            assigned=Assigned(self.assignee is not None),
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


class Linear(IssueTracker):
    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner

    @override
    def workspace_labels(self) -> LabelNames:
        lookup = Command(("linearis", "labels", "list", "--limit", "250"))
        found: list[LabelName] = []
        cursor: PageCursor | None = None
        while True:
            page = self._parsed(LabelPage.parse, self._paged(lookup, cursor))
            found.extend(page.names().root)
            cursor = page.next_cursor()
            if cursor is None:
                return LabelNames(tuple(found))

    @override
    def issues(self, wanted: IssueFilter) -> Issues:
        lookup = Command(
            (
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
        )
        found: list[Issue] = []
        cursor: PageCursor | None = None
        while True:
            page = self._parsed(IssuePage.parse, self._paged(lookup, cursor))
            found.extend(page.issues().root)
            cursor = page.next_cursor()
            if cursor is None:
                return Issues(tuple(found))

    @override
    def read(self, issue: IssueIdentifier) -> Issue:
        read = Command(("linearis", "issues", "read", issue.root))
        return self._parsed(IssuePayload.parse, read).issue()

    @override
    def add_label(self, issue: IssueIdentifier, label: LabelName) -> None:
        _ = self._run(
            Command(
                (
                    *self._update(issue).root,
                    "--labels",
                    label.root,
                    "--label-mode",
                    "add",
                )
            )
        )

    # linearis can add or overwrite labels but never remove one, so removal overwrites what is left.
    @override
    def set_labels(self, issue: IssueIdentifier, labels: LabelNames) -> None:
        if len(labels.root) == 0:
            _ = self._run(Command((*self._update(issue).root, "--clear-labels")))
            return
        names = ",".join(name.root for name in labels.root)
        _ = self._run(
            Command((*self._update(issue).root, "--labels", names, "--label-mode", "overwrite"))
        )

    @override
    def assign(self, issue: IssueIdentifier, assignee: Assignee) -> None:
        _ = self._run(Command((*self._update(issue).root, "--assignee", assignee.root)))

    @staticmethod
    def _update(issue: IssueIdentifier) -> Command:
        return Command(("linearis", "issues", "update", issue.root))

    @staticmethod
    def _paged(lookup: Command, cursor: PageCursor | None) -> Command:
        if cursor is None:
            return lookup
        return Command((*lookup.root, "--after", cursor.root))

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
