import tomllib
from pathlib import Path

from pydantic import model_validator

from mb_workflow.models import Model, Value


class MissingLinkError(Exception):
    pass


class InvalidLinkError(Exception):
    pass


class TaskId(Value[str]):
    # The identifier goes into a TOML string unescaped, so refuse anything that could close it.
    @model_validator(mode="after")
    def is_alphanumeric(self) -> TaskId:
        if not self.root.isalnum():
            raise ValueError(f"A Todoist task identifier is alphanumeric, unlike {self.root!r}.")
        return self

    @staticmethod
    def fake() -> TaskId:
        return TaskId("6hXJP7X5Q98fc9XR")


class LinkFileName(Value[str]):
    @staticmethod
    def fake() -> LinkFileName:
        return LinkFileName.default()

    @staticmethod
    def default() -> LinkFileName:
        return LinkFileName("mb-workflow.local.toml")


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
        return WorkspaceRoot(Path("/Users/me/orca/workspaces/mb-workflow/leaffish"))


class TaskLink(Model):
    task: TaskId

    @staticmethod
    def fake() -> TaskLink:
        return TaskLink(task=TaskId.fake())


class LinkPath(Value[Path]):
    @staticmethod
    def fake() -> LinkPath:
        return LinkPath.of(WorkspaceRoot.fake(), LinkFileName.fake())

    @staticmethod
    def of(root: WorkspaceRoot, name: LinkFileName) -> LinkPath:
        return LinkPath(root.root / name.root)

    def read(self) -> TaskLink | None:
        if not self.root.is_file():
            return None
        try:
            return TaskLink.model_validate(tomllib.loads(self.root.read_text()))
        except ValueError as error:
            raise InvalidLinkError(f"{self.root} is not valid. {error}") from error

    def write(self, link: TaskLink) -> None:
        _ = self.root.write_text(f'task = "{link.task.root}"\n')


class IgnorePath(Value[Path]):
    @staticmethod
    def fake() -> IgnorePath:
        return IgnorePath.of(WorkspaceRoot.fake(), IgnoreFileName.fake())

    @staticmethod
    def of(root: WorkspaceRoot, name: IgnoreFileName) -> IgnorePath:
        return IgnorePath(root.root / name.root)

    def ignore(self, name: LinkFileName) -> None:
        listed = self.root.read_text() if self.root.is_file() else ""
        if name.root in listed.splitlines():
            return
        opener = "" if listed == "" or listed.endswith("\n") else "\n"
        _ = self.root.write_text(f"{listed}{opener}{name.root}\n")


class WorkspaceLink(Model):
    workspace: WorkspaceRoot
    name: LinkFileName = LinkFileName.default()
    ignore_list: IgnoreFileName = IgnoreFileName.default()

    @staticmethod
    def fake() -> WorkspaceLink:
        return WorkspaceLink(workspace=WorkspaceRoot.fake())

    def path(self) -> LinkPath:
        return LinkPath.of(self.workspace, self.name)

    def ignore_path(self) -> IgnorePath:
        return IgnorePath.of(self.workspace, self.ignore_list)

    def read(self) -> TaskId | None:
        recorded = self.path().read()
        return recorded.task if recorded is not None else None

    def record(self, task: TaskId) -> None:
        self.path().write(TaskLink(task=task))
        self.ignore_path().ignore(self.name)

    def resolve(self, task: TaskId | None) -> TaskId:
        if task is not None:
            self.record(task)
            return task
        recorded = self.read()
        if recorded is None:
            raise MissingLinkError(
                f"No Todoist task is linked to this workspace. Supply one to record it in {self.path().root}."
            )
        return recorded
