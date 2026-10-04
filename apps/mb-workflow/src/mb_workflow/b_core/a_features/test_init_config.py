from typing import TYPE_CHECKING

from mb_workflow.b_core.a_features.init_config import Overwrite, init_config
from mb_workflow.b_core.d_domain_model.config import (
    ConfigExistsError,
    ConfigFileName,
    ConfigPath,
    WorkingDirectory,
)
from mb_workflow.b_core.d_domain_model.config_template import ConfigTemplate

if TYPE_CHECKING:
    from pathlib import Path


def test_writes_the_template_into_the_directory(tmp_path: Path) -> None:
    outcome = init_config(
        WorkingDirectory(tmp_path), ConfigFileName.fake(), ConfigTemplate.fake(), Overwrite(False)
    ).unwrap()

    assert outcome.written.root.read_text() == ConfigTemplate.fake().root


def test_refuses_to_overwrite_an_existing_config(tmp_path: Path) -> None:
    existing = tmp_path / ConfigFileName.fake().root
    _ = existing.write_text("kept")

    refused = init_config(
        WorkingDirectory(tmp_path), ConfigFileName.fake(), ConfigTemplate.fake(), Overwrite(False)
    )
    assert isinstance(refused.error, ConfigExistsError)
    assert existing.read_text() == "kept"


def test_overwrites_an_existing_config_when_asked(tmp_path: Path) -> None:
    _ = (tmp_path / ConfigFileName.fake().root).write_text("replaced")

    outcome = init_config(
        WorkingDirectory(tmp_path), ConfigFileName.fake(), ConfigTemplate.fake(), Overwrite(True)
    ).unwrap()

    assert outcome.written.root.read_text() == ConfigTemplate.fake().root


def test_reports_a_config_in_a_parent_directory_it_now_shadows(tmp_path: Path) -> None:
    parent = tmp_path / ConfigFileName.fake().root
    _ = parent.write_text("")
    child = tmp_path / "child"
    child.mkdir()

    outcome = init_config(
        WorkingDirectory(child), ConfigFileName.fake(), ConfigTemplate.fake(), Overwrite(False)
    ).unwrap()

    assert outcome.shadowed == ConfigPath(parent.resolve())


def test_ignores_a_config_above_the_repository_root(tmp_path: Path) -> None:
    _ = (tmp_path / ConfigFileName.fake().root).write_text("")
    repository = tmp_path / "repo"
    (repository / ".git").mkdir(parents=True)

    outcome = init_config(
        WorkingDirectory(repository), ConfigFileName.fake(), ConfigTemplate.fake(), Overwrite(False)
    ).unwrap()

    assert outcome.shadowed is None
