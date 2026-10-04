import re
from pathlib import Path
from subprocess import CalledProcessError
from typing import override

from pydantic import ValidationError
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)
from safe_result import Err, Ok, Result, safe_with

from mb_workflow.b_core.d_domain_model.config_override import SettingsTable
from mb_workflow.c_infrastructure.linear import LinearApiKey
from mb_workflow.c_infrastructure.shell import Command, CommandRunner
from mb_workflow.d_lib.models import Model, Value


class CredentialsError(Exception):
    pass


class MissingCredentialsError(CredentialsError):
    pass


class InvalidCredentialsError(CredentialsError):
    pass


class RepositorySlugError(Exception):
    pass


class NoOriginError(RepositorySlugError):
    pass


class UnreadableRemoteError(RepositorySlugError):
    pass


class RemoteUrl(Value[str]):
    @staticmethod
    def fake() -> RemoteUrl:
        return RemoteUrl("https://github.com/MartinBernstorff/mb-workflow.git")


# Keyed on the origin rather than the directory, because every worktree has its own directory name.
class RepositorySlug(Value[str]):
    @staticmethod
    def fake() -> RepositorySlug:
        return RepositorySlug("MartinBernstorff/mb-workflow")

    @staticmethod
    def of(remote: RemoteUrl) -> Result[RepositorySlug, UnreadableRemoteError]:
        found = re.search(r"[:/]([^/:]+/[^/:]+?)(?:\.git)?/?$", remote.root)
        if found is None:
            return Err(
                UnreadableRemoteError(f"Cannot read owner/repo from the remote {remote.root}.")
            )
        return Ok(RepositorySlug(found.group(1)))

    @staticmethod
    def of_origin(runner: CommandRunner) -> Result[RepositorySlug, RepositorySlugError]:
        match safe_with(CalledProcessError)(runner.run)(
            Command(("git", "remote", "get-url", "origin"))
        ):
            case Ok(output):
                return RepositorySlug.of(RemoteUrl(output.root.strip()))
            case Err(error):
                return Err(NoOriginError(f"Cannot read the origin remote. {error}"))


class LinearCredentials(Model):
    api_key: LinearApiKey
    integration_test_api_key: LinearApiKey | None = None

    @staticmethod
    def fake() -> LinearCredentials:
        return LinearCredentials(api_key=LinearApiKey.fake())


class ProjectCredentials(BaseSettings):
    model_config = SettingsConfigDict(extra="forbid", frozen=True)

    linear: LinearCredentials

    @staticmethod
    def fake() -> ProjectCredentials:
        return ProjectCredentials(linear=LinearCredentials.fake())

    @staticmethod
    def of_table(table: SettingsTable) -> Result[ProjectCredentials, ValidationError]:
        credential_tables = CredentialTables.of_credentials().root
        return safe_with(ValidationError)(ProjectCredentials)(
            **{key: value for key, value in table.root.items() if key in credential_tables}
        )

    # The file is the one source, so a stray environment variable cannot shadow a project's key.
    @override
    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings,)


# The same file holds the developer's project setting overrides, so credentials read only these.
class CredentialTables(Value[frozenset[str]]):
    @staticmethod
    def fake() -> CredentialTables:
        return CredentialTables.of_credentials()

    @staticmethod
    def of_credentials() -> CredentialTables:
        return CredentialTables(frozenset(ProjectCredentials.model_fields))


class CredentialsPath(Value[Path]):
    @staticmethod
    def fake() -> CredentialsPath:
        return CredentialsDirectory.fake().path_for(RepositorySlug.fake())

    def credentials(self) -> Result[ProjectCredentials, CredentialsError]:
        if not self.root.is_file():
            return Err(
                MissingCredentialsError(
                    f'No credentials at {self.root}. Create it with:\n[linear]\napi_key = "lin_api_…"'
                )
            )
        table = SettingsTable(TomlConfigSettingsSource(ProjectCredentials, self.root)())
        match ProjectCredentials.of_table(table):
            case Ok(credentials):
                return Ok(credentials)
            case Err(error):
                return Err(InvalidCredentialsError(f"{self.root} is not valid. {error}"))


class HomeDirectory(Value[Path]):
    @staticmethod
    def fake() -> HomeDirectory:
        return HomeDirectory(Path("/tmp/mb-workflow-fake/home"))

    @staticmethod
    def of_user() -> HomeDirectory:
        return HomeDirectory(Path.home())


class CredentialsDirectory(Value[Path]):
    @staticmethod
    def fake() -> CredentialsDirectory:
        return CredentialsDirectory(Path("/tmp/mb-workflow-fake/projects"))

    @staticmethod
    def of_user() -> CredentialsDirectory:
        return CredentialsDirectory.of_home(HomeDirectory.of_user())

    @staticmethod
    def of_home(home: HomeDirectory) -> CredentialsDirectory:
        return CredentialsDirectory(home.root / ".config" / "mb-workflow" / "projects")

    def path_for(self, repository: RepositorySlug) -> CredentialsPath:
        return CredentialsPath(self.root / f"{repository.root}.toml")

    def credentials_of_origin(
        self, runner: CommandRunner
    ) -> Result[ProjectCredentials, CredentialsError | RepositorySlugError]:
        match RepositorySlug.of_origin(runner):
            case Ok(repository):
                return self.path_for(repository).credentials()
            case Err() as failed:
                return failed
