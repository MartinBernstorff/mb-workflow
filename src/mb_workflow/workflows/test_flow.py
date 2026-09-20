from typing import TYPE_CHECKING

from mb_workflow.config import (
    ConfigFileName,
    Configuration,
    Settings,
    Tracker,
    WorkingDirectory,
)
from mb_workflow.shell import ExitCode
from mb_workflow.workflows.flow import FlowReport, show

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_reports_the_resolved_tracker_and_the_file_it_came_from() -> None:
    assert FlowReport.of(Configuration.fake()).root == (
        "tracker: todoist\n"
        "project tag: it-mb-workflow\n"
        "status store: workspace-board\n"
        "origin: /Users/me/orca/workspaces/mb-workflow/mb-workflow.toml"
    )


def test_a_linear_configuration_reports_no_project_tag() -> None:
    config = Configuration.fake().model_copy(update={"settings": Settings(tracker=Tracker.linear)})
    report = FlowReport.of(config)
    assert "tracker: linear" in report.root
    assert "project tag" not in report.root


def test_reporting_a_resolved_configuration_succeeds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _ = (tmp_path / "mb-workflow.toml").write_text('tracker = "linear"\n')

    assert show(WorkingDirectory(tmp_path), ConfigFileName.default()) == ExitCode(0)
    assert "tracker: linear" in capsys.readouterr().out


def test_an_absent_configuration_file_fails_the_command(tmp_path: Path) -> None:
    assert show(WorkingDirectory(tmp_path), ConfigFileName("absent.toml")) == ExitCode(1)


def test_an_unreadable_configuration_file_fails_the_command(tmp_path: Path) -> None:
    _ = (tmp_path / "mb-workflow.toml").write_text('tracker = "jira"\n')

    assert show(WorkingDirectory(tmp_path), ConfigFileName.default()) == ExitCode(1)
