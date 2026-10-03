import re
from pathlib import Path
from typing import override

from pydantic import ValidationError
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from mb_workflow.c_infrastructure.linear import LinearApiKey
from mb_workflow.c_infrastructure.shell import Command, CommandRunner
from mb_workflow.d_lib.models import Model, Value


class MissingCredentialsError(Exception):
    pass


class InvalidCredentialsError(Exception):
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
    def of(remote: RemoteUrl) -> RepositorySlug:
        found = re.search(r"[:/]([^/:]+/[^/:]+?)(?:\.git)?/?$", remote.root)
        if found is None:
            raise ValueError(f"Cannot read owner/repo from the remote {remote.root}.")
        return RepositorySlug(found.group(1))

    @staticmethod
    def of_origin(runner: CommandRunner) -> RepositorySlug:
        output = runner.run(Command(("git", "remote", "get-url", "origin")))
        return RepositorySlug.of(RemoteUrl(output.root.strip()))


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

    def credentials(self) -> ProjectCredentials:
        if not self.root.is_file():
            raise MissingCredentialsError(
                f'No credentials at {self.root}. Create it with:\n[linear]\napi_key = "lin_api_…"'
            )
        table = TomlConfigSettingsSource(ProjectCredentials, self.root)()
        credential_tables = CredentialTables.of_credentials().root
        try:
            return ProjectCredentials(
                **{key: value for key, value in table.items() if key in credential_tables}
            )
        except ValidationError as error:
            raise InvalidCredentialsError(f"{self.root} is not valid. {error}") from error


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
