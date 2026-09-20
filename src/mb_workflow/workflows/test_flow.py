from typing import TYPE_CHECKING

from mb_workflow.config import (
    ConfigFileName,
    ConfigPath,
    Configuration,
    LinearTracker,
    Settings,
    WorkingDirectory,
)
from mb_workflow.shell import ExitCode
from mb_workflow.workflows.flow import FlowReport, link, show
from mb_workflow.workspace.link import LinkFileName, TaskId, WorkspaceLink, WorkspaceRoot

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def linear_config(directory: WorkingDirectory) -> None:
    _ = (directory.root / ConfigFileName.default().root).write_text(
        '[issues]\ntracker = "linear"\n'
    )


def todoist_config(directory: WorkingDirectory) -> None:
    _ = (directory.root / ConfigFileName.default().root).write_text(
        '[issues]\ntracker = "todoist"\nproject_tag = "it-mb-workflow"\n'
    )


def recorded_link(directory: WorkingDirectory) -> WorkspaceLink:
    return WorkspaceLink(workspace=WorkspaceRoot(directory.root))


def test_reports_the_resolved_tracker_and_the_file_it_came_from() -> None:
    assert FlowReport.of(Configuration.fake(), TaskId.fake()).root == (
        "tracker: todoist\n"
        "project tag: it-mb-workflow\n"
        "task: 6hXJP7X5Q98fc9XR\n"
        "status store: orca\n"
        "origin: /Users/me/orca/workspaces/mb-workflow/mb-workflow.toml"
    )


def test_a_todoist_configuration_with_no_recorded_link_reports_no_task() -> None:
    assert "task: none" in FlowReport.of(Configuration.fake(), None).root


def test_a_linear_configuration_reports_no_project_tag() -> None:
    config = Configuration(settings=Settings(issues=LinearTracker.fake()), origin=ConfigPath.fake())

    report = FlowReport.of(config, None)

    assert "tracker: linear" in report.root
    assert "project tag" not in report.root


def test_reporting_a_resolved_configuration_succeeds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = WorkingDirectory(tmp_path)
    linear_config(directory)

    assert show(directory, ConfigFileName.fake()) == ExitCode(0)
    assert "tracker: linear" in capsys.readouterr().out


def test_an_absent_configuration_file_fails_the_command(tmp_path: Path) -> None:
    assert show(WorkingDirectory(tmp_path), ConfigFileName("absent.toml")) == ExitCode(1)


def test_a_malformed_configuration_file_fails_the_command(tmp_path: Path) -> None:
    _ = (tmp_path / "mb-workflow.toml").write_text('[issues]\ntracker = "jira"\n')

    assert show(WorkingDirectory(tmp_path), ConfigFileName.fake()) == ExitCode(1)


def test_showing_displays_the_linked_task(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = WorkingDirectory(tmp_path)
    todoist_config(directory)
    recorded_link(directory).record(TaskId.fake())

    assert show(directory, ConfigFileName.fake()) == ExitCode(0)
    assert "task: 6hXJP7X5Q98fc9XR" in capsys.readouterr().out


def test_showing_an_unlinked_todoist_workspace_succeeds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = WorkingDirectory(tmp_path)
    todoist_config(directory)

    assert show(directory, ConfigFileName.fake()) == ExitCode(0)
    assert "task: none" in capsys.readouterr().out


def test_showing_a_malformed_link_fails_the_command(tmp_path: Path) -> None:
    directory = WorkingDirectory(tmp_path)
    todoist_config(directory)
    _ = recorded_link(directory).path().root.write_text('taks = "6hXJP7X5Q98fc9XR"\n')

    assert show(directory, ConfigFileName.fake()) == ExitCode(1)


def test_linking_records_the_task_beside_the_configuration(tmp_path: Path) -> None:
    directory = WorkingDirectory(tmp_path)
    todoist_config(directory)

    assert link(directory, ConfigFileName.fake(), TaskId.fake()) == ExitCode(0)
    assert recorded_link(directory).read() == TaskId.fake()


def test_the_link_is_recorded_where_the_configuration_sits_not_where_the_command_ran(
    tmp_path: Path,
) -> None:
    root = WorkingDirectory(tmp_path)
    todoist_config(root)
    nested = tmp_path / "src"
    nested.mkdir()

    assert link(WorkingDirectory(nested), ConfigFileName.fake(), TaskId.fake()) == ExitCode(0)
    assert recorded_link(root).read() == TaskId.fake()
    assert not (nested / LinkFileName.default().root).exists()


def test_linking_again_without_a_task_reuses_the_recorded_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = WorkingDirectory(tmp_path)
    todoist_config(directory)
    _ = link(directory, ConfigFileName.fake(), TaskId.fake())
    _ = capsys.readouterr()

    assert link(directory, ConfigFileName.fake(), None) == ExitCode(0)
    assert capsys.readouterr().out == "6hXJP7X5Q98fc9XR\n"


def test_linking_adds_the_link_file_to_the_ignore_list(tmp_path: Path) -> None:
    directory = WorkingDirectory(tmp_path)
    todoist_config(directory)

    _ = link(directory, ConfigFileName.fake(), TaskId.fake())

    listed = recorded_link(directory).ignore_path().root.read_text().splitlines()
    assert LinkFileName.default().root in listed


def test_a_todoist_workspace_with_neither_a_record_nor_a_task_fails_the_command(
    tmp_path: Path,
) -> None:
    directory = WorkingDirectory(tmp_path)
    todoist_config(directory)

    assert link(directory, ConfigFileName.fake(), None) == ExitCode(1)


def test_linking_a_linear_workspace_fails_the_command(tmp_path: Path) -> None:
    directory = WorkingDirectory(tmp_path)
    linear_config(directory)

    assert link(directory, ConfigFileName.fake(), TaskId.fake()) == ExitCode(1)
