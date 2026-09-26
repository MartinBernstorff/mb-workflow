import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from mb_workflow.d_lib.models import Model, Value


class MissingConfigError(Exception):
    pass


class InvalidConfigError(Exception):
    pass


class TicketTracker(StrEnum):
    linear = "linear"
    todoist = "todoist"


class StatusStore(StrEnum):
    orca = "orca"


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


class LinearTracker(Model):
    tracker: Literal[TicketTracker.linear]

    @staticmethod
    def fake() -> LinearTracker:
        return LinearTracker(tracker=TicketTracker.linear)


class TodoistTracker(Model):
    tracker: Literal[TicketTracker.todoist]
    project_tag: ProjectTag

    @staticmethod
    def fake() -> TodoistTracker:
        return TodoistTracker(tracker=TicketTracker.todoist, project_tag=ProjectTag.fake())


class OrcaStatus(Model):
    store: Literal[StatusStore.orca] = StatusStore.orca

    @staticmethod
    def fake() -> OrcaStatus:
        return OrcaStatus(store=StatusStore.orca)


type TrackerSettings = Annotated[LinearTracker | TodoistTracker, Field(discriminator="tracker")]
type StatusSettings = OrcaStatus


class Settings(Model):
    issues: TrackerSettings
    status: StatusSettings = OrcaStatus()

    @staticmethod
    def fake() -> Settings:
        return Settings(issues=TodoistTracker.fake(), status=OrcaStatus.fake())


class ConfigPath(Value[Path]):
    @staticmethod
    def fake() -> ConfigPath:
        return ConfigPath(Path("/Users/me/orca/workspaces/mb-workflow/mb-workflow.toml"))

    def settings(self) -> Settings:
        try:
            return Settings.model_validate(tomllib.loads(self.root.read_text()))
        except ValueError as error:
            raise InvalidConfigError(f"{self.root} is not valid. {error}") from error


class WorkingDirectory(Value[Path]):
    @staticmethod
    def fake() -> WorkingDirectory:
        return WorkingDirectory(Path("/Users/me/orca/workspaces/mb-workflow"))


class SearchedDirectories(Value[tuple[Path, ...]]):
    @staticmethod
    def fake() -> SearchedDirectories:
        return SearchedDirectories.of(WorkingDirectory.fake())

    @staticmethod
    def of(directory: WorkingDirectory) -> SearchedDirectories:
        start = directory.root.resolve()
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
