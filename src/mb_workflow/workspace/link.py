import tomllib
from pathlib import Path
from typing import Annotated, Literal, Protocol, override

import tomli_w
from pydantic import Field, TypeAdapter, model_validator

from mb_workflow.config import ConfigPath, Tracker
from mb_workflow.issue import IssueIdentifier
from mb_workflow.models import Model, Value


class MissingLinkError(Exception):
    pass


class InvalidLinkError(Exception):
    pass


class TodoistTaskId(Value[str]):
    @model_validator(mode="after")
    def is_alphanumeric(self) -> TodoistTaskId:
        if not self.root.isalnum():
            raise ValueError(f"A Todoist task identifier is alphanumeric, unlike {self.root!r}.")
        return self

    @staticmethod
    def fake() -> TodoistTaskId:
        return TodoistTaskId("6hXJP7X5Q98fc9XR")


class SuppliedTicket(Value[str]):
    @staticmethod
    def fake() -> SuppliedTicket:
        return SuppliedTicket(TodoistTaskId.fake().root)


class TicketLinkFileName(Value[str]):
    @staticmethod
    def fake() -> TicketLinkFileName:
        return TicketLinkFileName.default()

    @staticmethod
    def default() -> TicketLinkFileName:
        return TicketLinkFileName("mb-workflow.local.toml")


class IgnoreFileName(Value[str]):
    @staticmethod
    def fake() -> IgnoreFileName:
        return IgnoreFileName.default()

    @staticmethod
    def default() -> IgnoreFileName:
        return IgnoreFileName(".gitignore")


class WorkspaceRoot(Value[Path]):
    @staticmethod
    def fake() -> WorkspaceRoot:
        return WorkspaceRoot.of(ConfigPath.fake())

    # The configuration file sits at the root of the repository it configures.
    @staticmethod
    def of(origin: ConfigPath) -> WorkspaceRoot:
        return WorkspaceRoot(origin.root.parent)


class TodoistTicketLink(Model):
    tracker: Literal[Tracker.todoist]
    task: TodoistTaskId

    @staticmethod
    def fake() -> TodoistTicketLink:
        return TodoistTicketLink.of(TodoistTaskId.fake())

    @staticmethod
    def of(task: TodoistTaskId) -> TodoistTicketLink:
        return TodoistTicketLink(tracker=Tracker.todoist, task=task)


class LinearTicketLink(Model):
    tracker: Literal[Tracker.linear]
    issue: IssueIdentifier

    @staticmethod
    def fake() -> LinearTicketLink:
        return LinearTicketLink.of(IssueIdentifier.fake())

    @staticmethod
    def of(issue: IssueIdentifier) -> LinearTicketLink:
        return LinearTicketLink(tracker=Tracker.linear, issue=issue)


type TicketLinkDocument = Annotated[
    TodoistTicketLink | LinearTicketLink, Field(discriminator="tracker")
]


class TicketLinkPath(Value[Path]):
    @staticmethod
    def fake() -> TicketLinkPath:
        return TicketLinkPath.of(WorkspaceRoot.fake(), TicketLinkFileName.fake())

    @staticmethod
    def of(root: WorkspaceRoot, name: TicketLinkFileName) -> TicketLinkPath:
        return TicketLinkPath(root.root / name.root)

    def read(self) -> TicketLinkDocument | None:
        if not self.root.is_file():
            return None
        try:
            return TypeAdapter[TicketLinkDocument](TicketLinkDocument).validate_python(
                tomllib.loads(self.root.read_text())
            )
        except ValueError as error:
            raise InvalidLinkError(f"{self.root} is not valid. {error}") from error

    def write(self, document: TicketLinkDocument) -> None:
        _ = self.root.write_text(tomli_w.dumps(document.model_dump(mode="json")))


class IgnorePath(Value[Path]):
    @staticmethod
    def fake() -> IgnorePath:
        return IgnorePath.of(WorkspaceRoot.fake(), IgnoreFileName.fake())

    @staticmethod
    def of(root: WorkspaceRoot, name: IgnoreFileName) -> IgnorePath:
        return IgnorePath(root.root / name.root)

    def ignore(self, name: TicketLinkFileName) -> None:
        listed = self.root.read_text() if self.root.is_file() else ""
        if name.root in (entry.strip() for entry in listed.splitlines()):
            return
        separator = "" if listed == "" or listed.endswith("\n") else "\n"
        _ = self.root.write_text(f"{listed}{separator}{name.root}\n")


class TicketLinkFile(Protocol):
    def path(self) -> TicketLinkPath: ...

    def read(self) -> TicketLinkDocument | None: ...

    def write(self, document: TicketLinkDocument) -> None: ...


class WorkspaceTicketLinkFile(TicketLinkFile):
    def __init__(
        self,
        workspace: WorkspaceRoot,
        name: TicketLinkFileName = TicketLinkFileName.default(),
        ignore_list: IgnoreFileName = IgnoreFileName.default(),
    ) -> None:
        self._workspace = workspace
        self._name = name
        self._ignore_list = ignore_list

    @override
    def path(self) -> TicketLinkPath:
        return TicketLinkPath.of(self._workspace, self._name)

    def ignore_path(self) -> IgnorePath:
        return IgnorePath.of(self._workspace, self._ignore_list)

    @override
    def read(self) -> TicketLinkDocument | None:
        return self.path().read()

    @override
    def write(self, document: TicketLinkDocument) -> None:
        self.path().write(document)
        self.ignore_path().ignore(self._name)


class MemoryTicketLinkFile(TicketLinkFile):
    def __init__(self, recorded: TicketLinkDocument | None = None) -> None:
        self._recorded = recorded

    @override
    def path(self) -> TicketLinkPath:
        return TicketLinkPath.fake()

    @override
    def read(self) -> TicketLinkDocument | None:
        return self._recorded

    @override
    def write(self, document: TicketLinkDocument) -> None:
        self._recorded = document


class TicketLinkStore[T](Protocol):
    def read(self) -> T | None: ...

    def record(self, linked: T) -> None: ...

    def parse(self, supplied: SuppliedTicket) -> T: ...

    def location(self) -> TicketLinkPath: ...

    def resolve(self, supplied: SuppliedTicket | None) -> T:
        if supplied is not None:
            linked = self.parse(supplied)
            self.record(linked)
            return linked
        recorded = self.read()
        if recorded is None:
            raise MissingLinkError(
                f"No ticket is linked to this workspace. Supply one to record it in {self.location().root}."
            )
        return recorded


class TodoistTicketLinkStore(TicketLinkStore[TodoistTaskId]):
    def __init__(self, file: TicketLinkFile) -> None:
        self._file = file

    @staticmethod
    def at(workspace: WorkspaceRoot) -> TodoistTicketLinkStore:
        return TodoistTicketLinkStore(WorkspaceTicketLinkFile(workspace))

    @override
    def location(self) -> TicketLinkPath:
        return self._file.path()

    @override
    def parse(self, supplied: SuppliedTicket) -> TodoistTaskId:
        return TodoistTaskId(supplied.root)

    @override
    def read(self) -> TodoistTaskId | None:
        match self._file.read():
            case TodoistTicketLink() as recorded:
                return recorded.task
            case LinearTicketLink():
                raise InvalidLinkError(
                    f"{self._file.path().root} links a Linear issue, but this workspace tracks issues on Todoist."
                )
            case None:
                return None

    @override
    def record(self, linked: TodoistTaskId) -> None:
        self._file.write(TodoistTicketLink.of(linked))


class LinearTicketLinkStore(TicketLinkStore[IssueIdentifier]):
    def __init__(self, file: TicketLinkFile) -> None:
        self._file = file

    @staticmethod
    def at(workspace: WorkspaceRoot) -> LinearTicketLinkStore:
        return LinearTicketLinkStore(WorkspaceTicketLinkFile(workspace))

    @override
    def location(self) -> TicketLinkPath:
        return self._file.path()

    @override
    def parse(self, supplied: SuppliedTicket) -> IssueIdentifier:
        return IssueIdentifier(supplied.root)

    @override
    def read(self) -> IssueIdentifier | None:
        match self._file.read():
            case LinearTicketLink() as recorded:
                return recorded.issue
            case TodoistTicketLink():
                raise InvalidLinkError(
                    f"{self._file.path().root} links a Todoist task, but this workspace tracks issues on Linear."
                )
            case None:
                return None

    @override
    def record(self, linked: IssueIdentifier) -> None:
        self._file.write(LinearTicketLink.of(linked))
