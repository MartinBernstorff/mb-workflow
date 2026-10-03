import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, ValidationError, field_validator, model_validator
from safe_result import Err, Ok, Result, safe_with

from mb_workflow.b_core.d_domain_model.config_override import (
    NoOverrideFile,
    OverrideFile,
    ProjectOverride,
    SettingKey,
    SettingSources,
    SettingsTable,
)
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

    @field_validator("orca_project")
    @classmethod
    def lowercased_orca_project(cls, project: ProjectSelector) -> ProjectSelector:
        # Orca stores project IDs in lowercase and matches them case-sensitively.
        return ProjectSelector(project.root.lower())


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

    @staticmethod
    @safe_with(ValidationError)
    def parsed(table: SettingsTable) -> Settings:
        return Settings.model_validate(table.root)

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

    def table(self) -> SettingsTable:
        try:
            return SettingsTable(tomllib.loads(self.root.read_text()))
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
        upward = (start, *start.parents)
        repository_root = next(
            (index for index, candidate in enumerate(upward) if (candidate / ".git").exists()),
            len(upward) - 1,
        )
        return SearchedDirectories(upward[: repository_root + 1])

    @staticmethod
    def above(directory: WorkingDirectory) -> SearchedDirectories:
        return SearchedDirectories(SearchedDirectories.of(directory).root[1:])

    def find(self, name: ConfigFileName) -> ConfigPath | None:
        return next(
            (
                ConfigPath(directory / name.root)
                for directory in self.root
                if (directory / name.root).is_file()
            ),
            None,
        )

    def listed(self) -> DirectoryListing:
        return DirectoryListing(", ".join(str(directory) for directory in self.root))


class DirectoryListing(Value[str]):
    @staticmethod
    def fake() -> DirectoryListing:
        return SearchedDirectories.fake().listed()


class NoRepoFile(Model):
    name: ConfigFileName
    searched: SearchedDirectories

    @staticmethod
    def fake() -> NoRepoFile:
        return NoRepoFile(name=ConfigFileName.fake(), searched=SearchedDirectories.fake())

    def missing(self, override: NoOverrideFile) -> MissingConfigError:
        expected = (
            "no origin remote to name a per-developer override file after"
            if override.expected is None
            else f"no per-developer override file at {override.expected.root}"
        )
        return MissingConfigError(
            f"No {self.name.root} found. Searched {self.searched.listed().root}, and {expected}."
        )


type RepoFile = ConfigPath | NoRepoFile


class Configuration(Model):
    settings: Settings
    origin: RepoFile
    table: SettingsTable
    override: ProjectOverride

    @staticmethod
    def fake() -> Configuration:
        return Configuration(
            settings=Settings.fake(),
            origin=ConfigPath.fake(),
            table=SettingsTable(
                {
                    **Settings.fake().model_dump(mode="json", exclude_none=True),
                    "ticket_statuses": {
                        state.root: status.root
                        for state, status in TicketStatuses.fake().root.items()
                    },
                }
            ),
            override=NoOverrideFile.fake(),
        )

    @staticmethod
    def resolved(
        directory: WorkingDirectory, name: ConfigFileName, override: ProjectOverride
    ) -> Result[Configuration, InvalidConfigError | MissingConfigError]:
        searched = SearchedDirectories.of(directory)
        origin = searched.find(name) or NoRepoFile(name=name, searched=searched)
        match origin:
            case NoRepoFile():
                if isinstance(override, NoOverrideFile):
                    return Err(origin.missing(override))
                table = SettingsTable.empty()
                merged = override.table
                described = f"{override.path.root} (with no {name.root} in the repository)"
            case ConfigPath():
                table = origin.table()
                merged = (
                    table.merged(override.table) if isinstance(override, OverrideFile) else table
                )
                overridden = (
                    f" with overrides from {override.path.root}"
                    if isinstance(override, OverrideFile)
                    else ""
                )
                described = f"{origin.root}{overridden}"
        match Settings.parsed(merged):
            case Ok(settings):
                return Ok(
                    Configuration(settings=settings, origin=origin, table=table, override=override)
                )
            case Err(error):
                return Err(InvalidConfigError(f"{described} is not valid. {error}"))

    def sources_of(self, key: SettingKey) -> SettingSources:
        return SettingSources.of(key, self.table, self.override)
