from typing import TYPE_CHECKING

from safe_result import Err, Ok

from mb_workflow.b_core.a_features.show_config import show_config
from mb_workflow.b_core.d_domain_model.config import (
    ConfigFileName,
    Configuration,
    InvalidConfigError,
    MissingConfigError,
    WorkingDirectory,
)
from mb_workflow.b_core.d_domain_model.config_override import (
    NoOverrideFile,
    OverrideFile,
    OverridePath,
    SettingsTable,
)
from mb_workflow.b_core.d_domain_model.issue import Assignee

if TYPE_CHECKING:
    from pathlib import Path


def with_repo_config(directory: WorkingDirectory) -> WorkingDirectory:
    _ = (directory.root / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "linear"\n'
        '[workspace]\norca_project = "github:flowbasedk/flowbase"\nassignee = "mab@flowbase.io"\n'
        '[ticket_statuses]\ngrill = "Maturing"\nto-ticket = "Maturing"\ntodo = "Todo"\n'
        'implementing = "In Progress"\nqa = "In Progress"\nreview = "In Review"\n'
        'merging = "Ready For Release"\nmerged = "Done"\n'
    )
    return directory


def test_reporting_a_resolved_configuration_succeeds(tmp_path: Path) -> None:
    directory = with_repo_config(WorkingDirectory(tmp_path))

    report = show_config(directory, ConfigFileName.fake(), NoOverrideFile.fake())

    assert "tracker: linear" in report.unwrap().root


def test_the_report_names_both_files_and_where_each_setting_came_from(tmp_path: Path) -> None:
    directory = with_repo_config(WorkingDirectory(tmp_path))
    override = OverrideFile(
        path=OverridePath(tmp_path / "override.toml"),
        table=SettingsTable({"workspace": {"assignee": "me@example.com"}}),
    )

    report = show_config(directory, ConfigFileName.fake(), override)

    lines = report.unwrap().root.splitlines()
    assert lines[:2] == [
        f"repo file: {(tmp_path / 'mb-workflow.toml').resolve()}",
        f"override file: {tmp_path / 'override.toml'}",
    ]
    assert "assignee: me@example.com (override)" in lines
    assert "orca project: github:flowbasedk/flowbase (repo)" in lines
    assert "claim label: workspace (default)" in lines


def test_the_report_notes_a_missing_override_file(tmp_path: Path) -> None:
    directory = with_repo_config(WorkingDirectory(tmp_path))
    override = NoOverrideFile(expected=OverridePath(tmp_path / "override.toml"))

    report = show_config(directory, ConfigFileName.fake(), override)

    assert (
        f"override file: none (no file at {tmp_path / 'override.toml'})"
        in report.unwrap().root.splitlines()
    )


def test_an_absent_configuration_file_is_an_error_value(tmp_path: Path) -> None:
    report = show_config(
        WorkingDirectory(tmp_path), ConfigFileName("absent.toml"), NoOverrideFile.fake()
    )

    assert isinstance(report, Err)
    assert isinstance(report.error, MissingConfigError)


def test_the_report_of_an_override_file_alone_notes_the_missing_repo_file(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    override = OverrideFile(
        path=OverridePath(tmp_path / "override.toml"), table=Configuration.fake().table
    )

    report = show_config(WorkingDirectory(tmp_path), ConfigFileName.fake(), override)

    lines = report.unwrap().root.splitlines()
    assert lines[:2] == [
        f"repo file: none (no {ConfigFileName.fake().root} in {tmp_path.resolve()})",
        f"override file: {tmp_path / 'override.toml'}",
    ]
    assert f"assignee: {Assignee.fake().root} (override)" in lines
    assert "status store: orca (override)" in lines


def test_a_malformed_configuration_file_is_an_error_value(tmp_path: Path) -> None:
    _ = (tmp_path / "mb-workflow.toml").write_text('[issues]\ntracker = "jira"\n')

    report = show_config(WorkingDirectory(tmp_path), ConfigFileName.fake(), NoOverrideFile.fake())

    assert isinstance(report, Err)
    assert isinstance(report.error, InvalidConfigError)


def test_an_override_breaking_the_configuration_is_an_error_value(tmp_path: Path) -> None:
    directory = with_repo_config(WorkingDirectory(tmp_path))
    override = OverrideFile(
        path=OverridePath(tmp_path / "override.toml"),
        table=SettingsTable({"issues": {"tracker": "jira"}}),
    )

    report = show_config(directory, ConfigFileName.fake(), override)

    assert not isinstance(report, Ok)
    assert str(tmp_path / "override.toml") in str(report.error)
