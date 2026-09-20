import tomllib
from enum import StrEnum
from pathlib import Path

from pydantic import model_validator

from mb_workflow.models import Model, Value


class MissingConfigError(Exception):
    pass


class Tracker(StrEnum):
    linear = "linear"
    todoist = "todoist"


class StatusStore(StrEnum):
    workspace_board = "workspace-board"


class ProjectTag(Value[str]):
    @staticmethod
    def fake() -> ProjectTag:
        return ProjectTag("it-mb-workflow")


class ConfigFileName(Value[str]):
    @staticmethod
    def fake() -> ConfigFileName:
        return ConfigFileName.default()

    @staticmethod
    def default() -> ConfigFileName:
        return ConfigFileName("mb-workflow.toml")


class Settings(Model):
    tracker: Tracker
    project_tag: ProjectTag | None = None
    status_store: StatusStore = StatusStore.workspace_board

    @staticmethod
    def fake() -> Settings:
        return Settings(
            tracker=Tracker.todoist,
            project_tag=ProjectTag.fake(),
            status_store=StatusStore.workspace_board,
        )

    @model_validator(mode="after")
    def the_project_tag_belongs_to_todoist(self) -> Settings:
        if self.tracker == Tracker.todoist and self.project_tag is None:
            raise ValueError(f'tracker = "{Tracker.todoist}" also needs a project_tag')
        if self.tracker != Tracker.todoist and self.project_tag is not None:
            raise ValueError(
                f'project_tag belongs to tracker = "{Tracker.todoist}", not "{self.tracker}"'
            )
        return self


class ConfigPath(Value[Path]):
    @staticmethod
    def fake() -> ConfigPath:
        return ConfigPath(Path("/Users/me/orca/workspaces/mb-workflow/mb-workflow.toml"))

    def settings(self) -> Settings:
        return Settings.model_validate(tomllib.loads(self.root.read_text()))


class WorkingDirectory(Value[Path]):
    @staticmethod
    def fake() -> WorkingDirectory:
        return WorkingDirectory(Path.cwd())


class SearchedDirectories(Value[tuple[Path, ...]]):
    @staticmethod
    def fake() -> SearchedDirectories:
        return SearchedDirectories.of(WorkingDirectory.fake())

    @staticmethod
    def of(directory: WorkingDirectory) -> SearchedDirectories:
        start = directory.root.absolute()
        return SearchedDirectories((start, *start.parents))

    def locate(self, name: ConfigFileName) -> ConfigPath:
        for directory in self.root:
            candidate = directory / name.root
            if candidate.is_file():
                return ConfigPath(candidate)
        listed = ", ".join(str(directory) for directory in self.root)
        raise MissingConfigError(f"No {name.root} found. Searched {listed}.")


class Configuration(Model):
    settings: Settings
    origin: ConfigPath

    @staticmethod
    def fake() -> Configuration:
        return Configuration(settings=Settings.fake(), origin=ConfigPath.fake())

    @staticmethod
    def resolved(directory: WorkingDirectory, name: ConfigFileName) -> Configuration:
        origin = SearchedDirectories.of(directory).locate(name)
        return Configuration(settings=origin.settings(), origin=origin)
