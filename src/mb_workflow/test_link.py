from typing import TYPE_CHECKING

import pytest

from mb_workflow.config import ConfigFileName, ConfigPath
from mb_workflow.link import (
    InvalidLinkError,
    LinkFileName,
    MissingLinkError,
    TaskId,
    WorkspaceLink,
    WorkspaceRoot,
)

if TYPE_CHECKING:
    from pathlib import Path


def other_task() -> TaskId:
    return TaskId("6hXJP3vMC467HcM2")


def test_the_workspace_root_is_the_directory_the_configuration_sits_in(tmp_path: Path) -> None:
    origin = ConfigPath(tmp_path / ConfigFileName.default().root)

    assert WorkspaceRoot.of(origin) == WorkspaceRoot(tmp_path)


def test_a_recorded_task_reads_back(tmp_path: Path) -> None:
    link = WorkspaceLink(workspace=WorkspaceRoot(tmp_path))

    link.record(TaskId.fake())

    assert link.read() == TaskId.fake()


def test_the_link_lives_in_a_file_at_the_workspace_root(tmp_path: Path) -> None:
    link = WorkspaceLink(workspace=WorkspaceRoot(tmp_path))

    link.record(TaskId.fake())

    assert link.path().root == tmp_path / LinkFileName.default().root
    assert link.path().root.is_file()


def test_a_workspace_with_nothing_recorded_reads_as_unlinked(tmp_path: Path) -> None:
    assert WorkspaceLink(workspace=WorkspaceRoot(tmp_path)).read() is None


def test_recording_a_second_task_replaces_the_first(tmp_path: Path) -> None:
    link = WorkspaceLink(workspace=WorkspaceRoot(tmp_path))

    link.record(TaskId.fake())
    link.record(other_task())

    assert link.read() == other_task()


def test_recording_adds_the_link_file_to_the_ignore_list(tmp_path: Path) -> None:
    link = WorkspaceLink(workspace=WorkspaceRoot(tmp_path))

    link.record(TaskId.fake())

    assert link.ignore_path().root.read_text() == f"{LinkFileName.default().root}\n"


def test_recording_twice_leaves_one_ignore_entry(tmp_path: Path) -> None:
    link = WorkspaceLink(workspace=WorkspaceRoot(tmp_path))

    link.record(TaskId.fake())
    link.record(other_task())

    listed = link.ignore_path().root.read_text().splitlines()
    assert listed.count(LinkFileName.default().root) == 1


def test_recording_keeps_the_entries_the_ignore_list_already_holds(tmp_path: Path) -> None:
    link = WorkspaceLink(workspace=WorkspaceRoot(tmp_path))
    _ = link.ignore_path().root.write_text(".venv/\n")

    link.record(TaskId.fake())

    assert link.ignore_path().root.read_text() == f".venv/\n{LinkFileName.default().root}\n"


def test_recording_starts_a_line_when_the_ignore_list_does_not_end_in_one(tmp_path: Path) -> None:
    link = WorkspaceLink(workspace=WorkspaceRoot(tmp_path))
    _ = link.ignore_path().root.write_text(".venv/")

    link.record(TaskId.fake())

    assert link.ignore_path().root.read_text() == f".venv/\n{LinkFileName.default().root}\n"


def test_a_supplied_task_is_recorded_as_it_is_resolved(tmp_path: Path) -> None:
    link = WorkspaceLink(workspace=WorkspaceRoot(tmp_path))

    assert link.resolve(TaskId.fake()) == TaskId.fake()
    assert link.read() == TaskId.fake()


def test_resolving_without_a_task_reuses_the_recorded_one(tmp_path: Path) -> None:
    link = WorkspaceLink(workspace=WorkspaceRoot(tmp_path))
    link.record(TaskId.fake())

    assert link.resolve(None) == TaskId.fake()


def test_resolving_with_neither_a_record_nor_a_task_names_the_file(tmp_path: Path) -> None:
    link = WorkspaceLink(workspace=WorkspaceRoot(tmp_path))

    with pytest.raises(MissingLinkError) as raised:
        _ = link.resolve(None)

    assert str(link.path().root) in str(raised.value)


def test_a_malformed_link_file_names_itself(tmp_path: Path) -> None:
    link = WorkspaceLink(workspace=WorkspaceRoot(tmp_path))
    _ = link.path().root.write_text('taks = "6hXJP7X5Q98fc9XR"\n')

    with pytest.raises(InvalidLinkError) as raised:
        _ = link.read()

    assert str(link.path().root) in str(raised.value)


def test_a_task_identifier_that_is_not_alphanumeric_is_refused() -> None:
    with pytest.raises(ValueError, match="alphanumeric"):
        _ = TaskId('6hXJ"\ntask = "other')
