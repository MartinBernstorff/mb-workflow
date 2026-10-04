import subprocess
from typing import TYPE_CHECKING

from assertions import Assert
from safe_result import Err, Ok

from mb_workflow.b_core.d_domain_model.config_override import (
    InvalidOverrideError,
    NoOverrideFile,
    OverrideFile,
    OverridePath,
    SettingsTable,
)
from mb_workflow.c_infrastructure.credentials import (
    CredentialsDirectory,
    HomeDirectory,
    RemoteUrl,
    RepositorySlug,
    UnreadableRemoteError,
)
from mb_workflow.c_infrastructure.linear import LinearApiKey
from mb_workflow.c_infrastructure.project_override import override_at, override_of_origin
from mb_workflow.c_infrastructure.shell import ExistingDirectory, Shell

if TYPE_CHECKING:
    from pathlib import Path


def test_a_missing_override_file_means_no_overrides(tmp_path: Path) -> None:
    path = OverridePath(tmp_path / "absent.toml")
    Assert.that(override_at(path)).matches(Ok(NoOverrideFile(expected=path)))


def test_an_override_file_yields_its_settings(tmp_path: Path) -> None:
    path = OverridePath(tmp_path / "repo.toml")
    _ = path.root.write_text('[workspace]\nassignee = "me@example.com"\n')

    table = SettingsTable({"workspace": {"assignee": "me@example.com"}})
    Assert.that(override_at(path)).matches(Ok(OverrideFile(path=path, table=table)))


def test_the_credentials_table_is_not_a_setting(tmp_path: Path) -> None:
    path = OverridePath(tmp_path / "repo.toml")
    _ = path.root.write_text(
        f'[linear]\napi_key = "{LinearApiKey.fake().root}"\n[claims]\nlabel = "mine"\n'
    )

    table = SettingsTable({"claims": {"label": "mine"}})
    Assert.that(override_at(path)).matches(Ok(OverrideFile(path=path, table=table)))


def test_invalid_toml_in_the_override_file_is_an_error_value(tmp_path: Path) -> None:
    path = OverridePath(tmp_path / "repo.toml")
    _ = path.root.write_text("[workspace\n")

    found = override_at(path)

    error = Assert.that(found.error).is_instance(InvalidOverrideError)
    Assert.that(str(error)).contains(str(path.root))


def test_an_unreadable_override_file_is_an_error_value(tmp_path: Path) -> None:
    path = OverridePath(tmp_path / "repo.toml")
    path.root.mkdir()

    _ = Assert.that(override_at(path)).is_instance(Err)


def test_the_override_file_is_named_after_the_origin_remote(tmp_path: Path) -> None:
    _ = subprocess.run(("git", "init", "-q"), cwd=tmp_path, check=True)
    _ = subprocess.run(
        ("git", "remote", "add", "origin", RemoteUrl.fake().root), cwd=tmp_path, check=True
    )
    directory = CredentialsDirectory.of_home(HomeDirectory(tmp_path / "home"))

    found = override_of_origin(directory, Shell(ExistingDirectory(tmp_path)))

    expected = OverridePath(directory.path_for(RepositorySlug.fake()).root)
    Assert.that(found).matches(Ok(NoOverrideFile(expected=expected)))


def test_a_repository_without_an_origin_remote_has_no_override_file(tmp_path: Path) -> None:
    _ = subprocess.run(("git", "init", "-q"), cwd=tmp_path, check=True)
    directory = CredentialsDirectory.of_home(HomeDirectory(tmp_path / "home"))

    found = override_of_origin(directory, Shell(ExistingDirectory(tmp_path)))

    Assert.that(found).matches(Ok(NoOverrideFile(expected=None)))


def test_an_origin_without_an_owner_is_an_unreadable_remote(tmp_path: Path) -> None:
    _ = subprocess.run(("git", "init", "-q"), cwd=tmp_path, check=True)
    _ = subprocess.run(("git", "remote", "add", "origin", "mb-workflow"), cwd=tmp_path, check=True)
    directory = CredentialsDirectory.of_home(HomeDirectory(tmp_path / "home"))

    found = override_of_origin(directory, Shell(ExistingDirectory(tmp_path)))

    _ = Assert.that(found.error).is_instance(UnreadableRemoteError)
