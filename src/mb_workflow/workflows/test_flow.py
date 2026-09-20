from typing import TYPE_CHECKING

import pytest

from mb_workflow.config import (
    ConfigFileName,
    ConfigPath,
    Configuration,
    LinearTracker,
    Settings,
    WorkingDirectory,
)
from mb_workflow.issue import IssueIdentifier
from mb_workflow.shell import ExitCode
from mb_workflow.workflows.flow import FlowReport, linked, shown
from mb_workflow.workflows.flow import link as link_command
from mb_workflow.workflows.flow import show as show_command
from mb_workflow.workspace.link import (
    LinearTicketLinkStore,
    MemoryTicketLinkFile,
    MissingLinkError,
    SuppliedTicket,
    TicketLinkFileName,
    TodoistTaskId,
    TodoistTicketLinkStore,
    WorkspaceRoot,
)

if TYPE_CHECKING:
    from pathlib import Path


def linear_config() -> Configuration:
    return Configuration(settings=Settings(issues=LinearTracker.fake()), origin=ConfigPath.fake())


def todoist_store() -> TodoistTicketLinkStore:
    return TodoistTicketLinkStore(MemoryTicketLinkFile())


def linear_store() -> LinearTicketLinkStore:
    return LinearTicketLinkStore(MemoryTicketLinkFile())


def test_reports_the_resolved_tracker_and_the_file_it_came_from() -> None:
    assert FlowReport.of(Configuration.fake(), TodoistTaskId.fake()).root == (
        "tracker: todoist\n"
        "project tag: it-mb-workflow\n"
        "task: 6hXJP7X5Q98fc9XR\n"
        "status store: orca\n"
        "origin: /Users/me/orca/workspaces/mb-workflow/mb-workflow.toml"
    )


def test_a_todoist_configuration_with_no_recorded_link_reports_no_task() -> None:
    assert "task: none" in FlowReport.of(Configuration.fake(), None).root


def test_a_linear_configuration_reports_its_issue_and_no_project_tag() -> None:
    report = FlowReport.of(linear_config(), IssueIdentifier.fake())

    assert "tracker: linear" in report.root
    assert "issue: E-4289" in report.root
    assert "project tag" not in report.root


def test_a_linear_configuration_with_no_recorded_link_reports_no_issue() -> None:
    assert "issue: none" in FlowReport.of(linear_config(), None).root


def test_showing_displays_the_recorded_task() -> None:
    store = todoist_store()
    store.record(TodoistTaskId.fake())

    assert "task: 6hXJP7X5Q98fc9XR" in shown(Configuration.fake(), store).root


def test_showing_an_unlinked_workspace_reports_no_ticket() -> None:
    assert "task: none" in shown(Configuration.fake(), todoist_store()).root


def test_showing_a_linear_workspace_displays_the_recorded_issue() -> None:
    store = linear_store()
    store.record(IssueIdentifier.fake())

    assert "issue: E-4289" in shown(linear_config(), store).root


def test_linking_records_the_supplied_ticket() -> None:
    store = todoist_store()

    assert linked(store, SuppliedTicket.fake()) == TodoistTaskId.fake()
    assert store.read() == TodoistTaskId.fake()


def test_linking_again_without_a_ticket_reuses_the_recorded_one() -> None:
    store = linear_store()
    store.record(IssueIdentifier.fake())

    assert linked(store, None) == IssueIdentifier.fake()


def test_a_workspace_with_neither_a_record_nor_a_ticket_is_an_error() -> None:
    with pytest.raises(MissingLinkError):
        _ = linked(todoist_store(), None)


def test_reporting_a_resolved_configuration_succeeds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _ = (tmp_path / ConfigFileName.default().root).write_text('[issues]\ntracker = "linear"\n')

    assert show_command(WorkingDirectory(tmp_path), ConfigFileName.fake()) == ExitCode(0)
    assert "tracker: linear" in capsys.readouterr().out


def test_an_absent_configuration_file_fails_the_command(tmp_path: Path) -> None:
    assert show_command(WorkingDirectory(tmp_path), ConfigFileName("absent.toml")) == ExitCode(1)


def test_a_malformed_configuration_file_fails_the_command(tmp_path: Path) -> None:
    _ = (tmp_path / ConfigFileName.default().root).write_text('[issues]\ntracker = "jira"\n')

    assert show_command(WorkingDirectory(tmp_path), ConfigFileName.fake()) == ExitCode(1)


def test_the_link_is_recorded_where_the_configuration_sits_not_where_the_command_ran(
    tmp_path: Path,
) -> None:
    _ = (tmp_path / ConfigFileName.default().root).write_text(
        '[issues]\ntracker = "todoist"\nproject_tag = "it-mb-workflow"\n'
    )
    nested = tmp_path / "src"
    nested.mkdir()

    supplied = SuppliedTicket.fake()
    assert link_command(WorkingDirectory(nested), ConfigFileName.fake(), supplied) == ExitCode(0)

    recorded = TodoistTicketLinkStore.at(WorkspaceRoot(tmp_path))
    assert recorded.read() == TodoistTaskId.fake()
    assert not (nested / TicketLinkFileName.default().root).exists()


def test_a_workspace_with_nothing_to_link_fails_the_command(tmp_path: Path) -> None:
    _ = (tmp_path / ConfigFileName.default().root).write_text(
        '[issues]\ntracker = "todoist"\nproject_tag = "it-mb-workflow"\n'
    )

    assert link_command(WorkingDirectory(tmp_path), ConfigFileName.fake(), None) == ExitCode(1)
