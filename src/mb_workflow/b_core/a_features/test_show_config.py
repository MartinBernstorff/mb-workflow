from typing import TYPE_CHECKING

import pytest

from mb_workflow.b_core.a_features.show_config import show_config
from mb_workflow.b_core.d_domain_model.config import (
    ConfigFileName,
    InvalidConfigError,
    MissingConfigError,
    WorkingDirectory,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_reporting_a_resolved_configuration_succeeds(tmp_path: Path) -> None:
    _ = (tmp_path / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "linear"\n'
        '[workspace]\norca_project = "github:flowbasedk/flowbase"\nassignee = "mab@flowbase.io"\n'
        '[ticket_statuses]\nGrilling = "Maturing"\nSpeccing = "Maturing"\nSpecced = "Todo"\n'
        'Implementing = "In Progress"\nQA = "In Progress"\nReview = "In Review"\n'
        'Merging = "Ready For Release"\nMerged = "Done"\n'
    )

    report = show_config(WorkingDirectory(tmp_path), ConfigFileName.fake())

    assert "tracker: linear" in report.root


def test_an_absent_configuration_file_fails_the_command(tmp_path: Path) -> None:
    with pytest.raises(MissingConfigError):
        _ = show_config(WorkingDirectory(tmp_path), ConfigFileName("absent.toml"))


def test_a_malformed_configuration_file_fails_the_command(tmp_path: Path) -> None:
    _ = (tmp_path / "mb-workflow.toml").write_text('[issues]\ntracker = "jira"\n')

    with pytest.raises(InvalidConfigError):
        _ = show_config(WorkingDirectory(tmp_path), ConfigFileName.fake())
