import pytest

from mb_workflow.flow import StateName, StateNames
from mb_workflow.shell import Command
from mb_workflow.workspace.board import BoardError, Column, Columns, StateColumns
from mb_workflow.workspace.orca import (
    ColumnLabel,
    ErrorMessage,
    WorkspaceStatus,
    WorktreeSelector,
)

REFUSAL = ErrorMessage(
    'Unknown workspace status "zzz". Available: status-8-2 (Tomorrow), in-progress (Grilling), '
    "status-9 (Speccing), status-5-2 (Implementing), status-8 (Me reviewing others), "
    "in-review (My QA), status-5 (Awaiting review), completed (Merging), status-6 (Merged)."
)


def board() -> Columns:
    return Columns.parse(REFUSAL)


def test_reads_the_id_to_label_table_from_the_columns_orca_names() -> None:
    assert board().label_of(WorkspaceStatus("status-5-2")) == ColumnLabel("Implementing")
    assert board().id_of(ColumnLabel("Me reviewing others")) == WorkspaceStatus("status-8")


def test_reads_every_column_orca_names() -> None:
    assert len(board().root) == 9


def test_a_refusal_naming_no_columns_is_a_clear_error() -> None:
    with pytest.raises(BoardError, match="named no board columns"):
        _ = Columns.parse(ErrorMessage("Unknown workspace status. Available: ."))


def test_an_id_the_board_does_not_define_has_no_label() -> None:
    assert board().label_of(WorkspaceStatus("status-404")) is None


def test_every_state_the_chart_holds_has_a_board_column() -> None:
    assert (
        StateNames(frozenset(pairing.state for pairing in StateColumns.of_chart().root))
        == StateNames.of_chart()
    )


def test_a_column_id_resolves_to_the_state_its_label_stands_for() -> None:
    assert board().state_of(WorkspaceStatus("in-review")) == StateName("QA")


def test_a_column_outside_the_chart_reads_as_the_start_state() -> None:
    assert board().state_of(WorkspaceStatus("status-8")) == StateNames.start()


def test_a_workspace_with_no_column_reads_as_the_start_state() -> None:
    assert board().state_of(None) == StateNames.start()


def test_a_column_the_board_no_longer_defines_reads_as_the_start_state() -> None:
    assert board().state_of(WorkspaceStatus("status-404")) == StateNames.start()


def test_a_state_maps_to_the_board_column_its_label_names() -> None:
    assert board().column_for(StateName("Review")) == ColumnLabel("Awaiting review")


def test_a_state_the_board_has_no_column_for_is_a_clear_error() -> None:
    columns = Columns((Column(id=WorkspaceStatus("in-progress"), label=ColumnLabel("Grilling")),))
    with pytest.raises(BoardError, match="defines no Merged column"):
        _ = columns.column_for(StateName("Merged"))


def test_a_state_outside_the_chart_has_no_board_column() -> None:
    with pytest.raises(BoardError, match="no board column"):
        _ = StateColumns.of_chart().label_of(StateName("Abandoned"))


def test_a_state_is_written_to_the_board_by_its_column_label() -> None:
    assignment = board().column_for(StateName("Review")).assignment(WorktreeSelector.current())
    assert assignment == Command(
        (
            "orca",
            "worktree",
            "set",
            "--worktree",
            "current",
            "--workspace-status",
            "Awaiting review",
            "--json",
        )
    )
