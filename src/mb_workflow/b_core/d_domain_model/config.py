import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from mb_workflow.b_core.d_domain_model.issue import Assignee, LabelName, ProjectName, TeamKey
from mb_workflow.b_core.d_domain_model.pool import PoolLimits, ViewSlug
from mb_workflow.b_core.d_domain_model.ticket_draft import TicketDefaults
from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses
from mb_workflow.b_core.d_domain_model.workspace import ProjectSelector
from mb_workflow.d_lib.models import Model, Value


class MissingConfigError(Exception):
    pass


class InvalidConfigError(Exception):
    pass


class ConfigExistsError(Exception):
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
    team: TeamKey | None = None
    project: ProjectName | None = None

    @staticmethod
    def fake() -> LinearTracker:
        return LinearTracker(tracker=TicketTracker.linear, team=None, project=ProjectName.fake())

    def ticket_defaults(self) -> TicketDefaults:
        return TicketDefaults(team=self.team, project=self.project)


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


class WorkspaceSettings(Model):
    orca_project: ProjectSelector
    assignee: Assignee

    @staticmethod
    def fake() -> WorkspaceSettings:
        return WorkspaceSettings(orca_project=ProjectSelector.fake(), assignee=Assignee.fake())


class ClaimSettings(Model):
    label: LabelName = LabelName("workspace")

    @staticmethod
    def fake() -> ClaimSettings:
        return ClaimSettings(label=LabelName("claimed"))


class PoolSettings(Model):
    view: ViewSlug
    limits: PoolLimits = PoolLimits()
    skip_limits_label: LabelName = LabelName("skip-limits")

    @staticmethod
    def fake() -> PoolSettings:
        return PoolSettings(view=ViewSlug.fake(), limits=PoolLimits.fake())


type TrackerSettings = Annotated[LinearTracker | TodoistTracker, Field(discriminator="tracker")]
type StatusSettings = OrcaStatus


class Settings(Model):
    issues: TrackerSettings
    status: StatusSettings = OrcaStatus()
    workspace: WorkspaceSettings
    claims: ClaimSettings = ClaimSettings()
    pool: PoolSettings | None = None
    ticket_statuses: TicketStatuses

    @staticmethod
    def fake() -> Settings:
        return Settings(
            issues=TodoistTracker.fake(),
            status=OrcaStatus.fake(),
            workspace=WorkspaceSettings.fake(),
            claims=ClaimSettings.fake(),
            pool=None,
            ticket_statuses=TicketStatuses.fake(),
        )

    # The pool is a Linear view, so no other tracker can supply its tickets.
    @model_validator(mode="after")
    def pool_is_a_linear_view(self) -> Settings:
        if self.pool is not None and not isinstance(self.issues, LinearTracker):
            raise ValueError("[pool] needs the linear tracker.")
        return self

    def ticket_defaults(self) -> TicketDefaults:
        if not isinstance(self.issues, LinearTracker):
            raise InvalidConfigError("Creating a ticket needs the linear tracker.")
        return self.issues.ticket_defaults()

    def required_pool(self) -> PoolSettings:
        if self.pool is None:
            raise InvalidConfigError('Set [pool] view = "<slug>" to name the Linear view to drain.')
        return self.pool


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

    @staticmethod
    def above(directory: WorkingDirectory) -> SearchedDirectories:
        return SearchedDirectories(tuple(directory.root.resolve().parents))

    def find(self, name: ConfigFileName) -> ConfigPath | None:
        return next(
            (
                ConfigPath(directory / name.root)
                for directory in self.root
                if (directory / name.root).is_file()
            ),
            None,
        )

    def locate(self, name: ConfigFileName) -> ConfigPath:
        found = self.find(name)
        if found is not None:
            return found
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
