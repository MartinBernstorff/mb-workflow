import subprocess
from typing import TYPE_CHECKING

import pytest

from mb_workflow.c_infrastructure.credentials import (
    CredentialsDirectory,
    InvalidCredentialsError,
    MissingCredentialsError,
    ProjectCredentials,
    RemoteUrl,
    RepositorySlug,
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
    assert RepositorySlug.of(RemoteUrl(remote)) == RepositorySlug.fake()


def test_a_remote_without_an_owner_is_refused() -> None:
    with pytest.raises(ValueError, match="owner/repo"):
        _ = RepositorySlug.of(RemoteUrl("mb-workflow"))


def test_the_repository_is_read_from_the_origin_remote(tmp_path: Path) -> None:
    _ = subprocess.run(("git", "init", "-q"), cwd=tmp_path, check=True)
    _ = subprocess.run(
        ("git", "remote", "add", "origin", RemoteUrl.fake().root), cwd=tmp_path, check=True
    )
    assert RepositorySlug.of_origin(Shell(ExistingDirectory(tmp_path))) == RepositorySlug.fake()


def test_a_project_s_credentials_are_read_from_its_file(tmp_path: Path) -> None:
    path = CredentialsDirectory(tmp_path).path_for(RepositorySlug.fake())
    path.root.parent.mkdir(parents=True)
    _ = path.root.write_text(f'[linear]\napi_key = "{LinearApiKey.fake().root}"\n')

    assert path.credentials() == ProjectCredentials.fake()


def test_a_project_without_a_credentials_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(MissingCredentialsError):
        _ = CredentialsDirectory(tmp_path).path_for(RepositorySlug.fake()).credentials()


def test_a_credentials_file_without_a_linear_key_is_refused(tmp_path: Path) -> None:
    path = CredentialsDirectory(tmp_path).path_for(RepositorySlug.fake())
    path.root.parent.mkdir(parents=True)
    _ = path.root.write_text("[linear]\n")

    with pytest.raises(InvalidCredentialsError):
        _ = path.credentials()
