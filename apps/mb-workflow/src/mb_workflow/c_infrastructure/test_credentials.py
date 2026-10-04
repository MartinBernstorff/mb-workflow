import subprocess
from typing import TYPE_CHECKING

import pytest
from assertions import Assert
from safe_result import Ok

from mb_workflow.b_core.d_domain_model.config_override import SettingsTable
from mb_workflow.c_infrastructure.credentials import (
    CredentialsDirectory,
    InvalidCredentialsError,
    MissingCredentialsError,
    NoOriginError,
    ProjectCredentials,
    RemoteUrl,
    RepositorySlug,
    UnreadableRemoteError,
)
from mb_workflow.c_infrastructure.linear import LinearApiKey
from mb_workflow.c_infrastructure.shell import ExistingDirectory, Shell

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    "remote",
    [
        "https://github.com/MartinBernstorff/mb-workflow.git",
        "https://github.com/MartinBernstorff/mb-workflow",
        "git@github.com:MartinBernstorff/mb-workflow.git",
        "ssh://git@github.com/MartinBernstorff/mb-workflow.git",
    ],
)
def test_the_repository_is_read_from_any_remote_form(remote: str) -> None:
    Assert.that(RepositorySlug.of(RemoteUrl(remote))).matches(Ok(RepositorySlug.fake()))


def test_a_remote_without_an_owner_is_refused() -> None:
    read = RepositorySlug.of(RemoteUrl("mb-workflow"))
    _ = Assert.that(read).is_err(UnreadableRemoteError)


def test_the_repository_is_read_from_the_origin_remote(tmp_path: Path) -> None:
    _ = subprocess.run(("git", "init", "-q"), cwd=tmp_path, check=True)
    _ = subprocess.run(
        ("git", "remote", "add", "origin", RemoteUrl.fake().root), cwd=tmp_path, check=True
    )
    Assert.that(RepositorySlug.of_origin(Shell(ExistingDirectory(tmp_path)))).matches(
        Ok(RepositorySlug.fake())
    )


def test_a_repository_without_an_origin_is_refused(tmp_path: Path) -> None:
    _ = subprocess.run(("git", "init", "-q"), cwd=tmp_path, check=True)
    read = RepositorySlug.of_origin(Shell(ExistingDirectory(tmp_path)))
    _ = Assert.that(read).is_err(NoOriginError)


def test_a_project_s_credentials_are_read_from_its_file(tmp_path: Path) -> None:
    path = CredentialsDirectory(tmp_path).path_for(RepositorySlug.fake())
    path.root.parent.mkdir(parents=True)
    _ = path.root.write_text(f'[linear]\napi_key = "{LinearApiKey.fake().root}"\n')

    Assert.that(path.credentials()).matches(Ok(ProjectCredentials.fake()))


def test_a_project_without_a_credentials_file_is_refused(tmp_path: Path) -> None:
    read = CredentialsDirectory(tmp_path).path_for(RepositorySlug.fake()).credentials()
    _ = Assert.that(read).is_err(MissingCredentialsError)


def test_credentials_without_a_linear_key_are_refused() -> None:
    _ = Assert.that(ProjectCredentials.of_table(SettingsTable({"linear": {}}))).is_err(Exception)


def test_project_settings_beside_the_credentials_are_not_credentials() -> None:
    table = SettingsTable(
        {"linear": {"api_key": LinearApiKey.fake().root}} | SettingsTable.fake().root
    )
    Assert.that(ProjectCredentials.of_table(table)).matches(Ok(ProjectCredentials.fake()))


def test_an_invalid_credentials_file_is_refused(tmp_path: Path) -> None:
    path = CredentialsDirectory(tmp_path).path_for(RepositorySlug.fake())
    path.root.parent.mkdir(parents=True)
    _ = path.root.write_text("[linear]\n")

    read = path.credentials()
    _ = Assert.that(read).is_err(InvalidCredentialsError)
