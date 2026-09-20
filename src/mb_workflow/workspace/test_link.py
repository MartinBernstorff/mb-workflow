from typing import TYPE_CHECKING

import pytest

from mb_workflow.config import ConfigFileName, ConfigPath
from mb_workflow.issue import IssueIdentifier
from mb_workflow.workspace.link import (
    InvalidLinkError,
    LinearTicketLink,
    LinearTicketLinkStore,
    MemoryTicketLinkFile,
    MissingLinkError,
    SuppliedTicket,
    TicketLinkFile,
    TicketLinkFileName,
    TodoistTaskId,
    TodoistTicketLink,
    TodoistTicketLinkStore,
    WorkspaceRoot,
    WorkspaceTicketLinkFile,
)

if TYPE_CHECKING:
    from pathlib import Path


def other_task() -> TodoistTaskId:
    return TodoistTaskId("6hXJP3vMC467HcM2")


def other_issue() -> IssueIdentifier:
    return IssueIdentifier("E-1234")


@pytest.fixture(params=["workspace", "memory"])
def file(request: pytest.FixtureRequest, tmp_path: Path) -> TicketLinkFile:
    if request.param == "memory":
        return MemoryTicketLinkFile()
    return WorkspaceTicketLinkFile(WorkspaceRoot(tmp_path))


def test_the_workspace_root_is_the_directory_the_configuration_sits_in(tmp_path: Path) -> None:
    origin = ConfigPath(tmp_path / ConfigFileName.default().root)

    assert WorkspaceRoot.of(origin) == WorkspaceRoot(tmp_path)


def test_a_recorded_task_reads_back(file: TicketLinkFile) -> None:
    store = TodoistTicketLinkStore(file)

    store.record(TodoistTaskId.fake())

    assert store.read() == TodoistTaskId.fake()


def test_a_recorded_issue_reads_back(file: TicketLinkFile) -> None:
    store = LinearTicketLinkStore(file)

    store.record(IssueIdentifier.fake())

    assert store.read() == IssueIdentifier.fake()


def test_a_workspace_with_nothing_recorded_reads_as_unlinked(file: TicketLinkFile) -> None:
    assert TodoistTicketLinkStore(file).read() is None


def test_recording_a_second_ticket_replaces_the_first(file: TicketLinkFile) -> None:
    store = TodoistTicketLinkStore(file)

    store.record(TodoistTaskId.fake())
    store.record(other_task())

    assert store.read() == other_task()


def test_a_supplied_ticket_is_recorded_as_it_is_resolved(file: TicketLinkFile) -> None:
    store = TodoistTicketLinkStore(file)

    assert store.resolve(SuppliedTicket.fake()) == TodoistTaskId.fake()
    assert store.read() == TodoistTaskId.fake()


def test_resolving_without_a_ticket_reuses_the_recorded_one(file: TicketLinkFile) -> None:
    store = LinearTicketLinkStore(file)
    store.record(IssueIdentifier.fake())

    assert store.resolve(None) == IssueIdentifier.fake()


def test_resolving_with_neither_a_record_nor_a_ticket_names_the_file(file: TicketLinkFile) -> None:
    store = TodoistTicketLinkStore(file)

    with pytest.raises(MissingLinkError) as raised:
        _ = store.resolve(None)

    assert str(store.location().root) in str(raised.value)


def test_a_todoist_store_refuses_a_workspace_linked_to_a_linear_issue(
    file: TicketLinkFile,
) -> None:
    file.write(LinearTicketLink.fake())

    with pytest.raises(InvalidLinkError, match="links a Linear issue"):
        _ = TodoistTicketLinkStore(file).read()


def test_a_linear_store_refuses_a_workspace_linked_to_a_todoist_task(file: TicketLinkFile) -> None:
    file.write(TodoistTicketLink.fake())

    with pytest.raises(InvalidLinkError, match="links a Todoist task"):
        _ = LinearTicketLinkStore(file).read()


def test_a_linear_workspace_accepts_an_identifier_a_todoist_one_would_refuse(
    file: TicketLinkFile,
) -> None:
    assert LinearTicketLinkStore(file).resolve(SuppliedTicket(other_issue().root)) == other_issue()


def test_a_todoist_workspace_refuses_an_identifier_that_is_not_alphanumeric(
    file: TicketLinkFile,
) -> None:
    with pytest.raises(ValueError, match="alphanumeric"):
        _ = TodoistTicketLinkStore(file).resolve(SuppliedTicket(other_issue().root))


def test_the_link_lives_in_a_file_at_the_workspace_root(tmp_path: Path) -> None:
    store = TodoistTicketLinkStore(WorkspaceTicketLinkFile(WorkspaceRoot(tmp_path)))

    store.record(TodoistTaskId.fake())

    assert store.location().root == tmp_path / TicketLinkFileName.default().root
    assert store.location().root.is_file()


def test_the_recorded_file_names_the_tracker_that_wrote_it(tmp_path: Path) -> None:
    TodoistTicketLinkStore(WorkspaceTicketLinkFile(WorkspaceRoot(tmp_path))).record(
        TodoistTaskId.fake()
    )

    written = (tmp_path / TicketLinkFileName.default().root).read_text()
    assert 'tracker = "todoist"' in written
    assert f'task = "{TodoistTaskId.fake().root}"' in written


def test_an_issue_identifier_survives_the_round_trip_through_the_file(tmp_path: Path) -> None:
    store = LinearTicketLinkStore(WorkspaceTicketLinkFile(WorkspaceRoot(tmp_path)))

    store.record(IssueIdentifier.fake())

    assert store.read() == IssueIdentifier.fake()


def test_a_malformed_link_file_names_itself(tmp_path: Path) -> None:
    file = WorkspaceTicketLinkFile(WorkspaceRoot(tmp_path))
    _ = file.path().root.write_text('tracker = "todoist"\ntaks = "6hXJP7X5Q98fc9XR"\n')

    with pytest.raises(InvalidLinkError) as raised:
        _ = TodoistTicketLinkStore(file).read()

    assert str(file.path().root) in str(raised.value)


def test_a_link_file_naming_no_tracker_is_refused(tmp_path: Path) -> None:
    file = WorkspaceTicketLinkFile(WorkspaceRoot(tmp_path))
    _ = file.path().root.write_text('task = "6hXJP7X5Q98fc9XR"\n')

    with pytest.raises(InvalidLinkError):
        _ = TodoistTicketLinkStore(file).read()


def test_recording_adds_the_link_file_to_the_ignore_list(tmp_path: Path) -> None:
    file = WorkspaceTicketLinkFile(WorkspaceRoot(tmp_path))

    TodoistTicketLinkStore(file).record(TodoistTaskId.fake())

    assert file.ignore_path().root.read_text() == f"{TicketLinkFileName.default().root}\n"


def test_recording_twice_leaves_one_ignore_entry(tmp_path: Path) -> None:
    file = WorkspaceTicketLinkFile(WorkspaceRoot(tmp_path))
    store = TodoistTicketLinkStore(file)

    store.record(TodoistTaskId.fake())
    store.record(other_task())

    listed = file.ignore_path().root.read_text().splitlines()
    assert listed.count(TicketLinkFileName.default().root) == 1


def test_recording_keeps_the_entries_the_ignore_list_already_holds(tmp_path: Path) -> None:
    file = WorkspaceTicketLinkFile(WorkspaceRoot(tmp_path))
    _ = file.ignore_path().root.write_text(".venv/\n")

    TodoistTicketLinkStore(file).record(TodoistTaskId.fake())

    assert file.ignore_path().root.read_text() == f".venv/\n{TicketLinkFileName.default().root}\n"


def test_recording_starts_a_line_when_the_ignore_list_does_not_end_in_one(tmp_path: Path) -> None:
    file = WorkspaceTicketLinkFile(WorkspaceRoot(tmp_path))
    _ = file.ignore_path().root.write_text(".venv/")

    TodoistTicketLinkStore(file).record(TodoistTaskId.fake())

    assert file.ignore_path().root.read_text() == f".venv/\n{TicketLinkFileName.default().root}\n"


def test_a_task_identifier_that_is_not_alphanumeric_is_refused() -> None:
    with pytest.raises(ValueError, match="alphanumeric"):
        _ = TodoistTaskId('6hXJ"\ntask = "other')
