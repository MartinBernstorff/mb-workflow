from safe_result import Err, Ok, Result

from mb_workflow.b_core.c_secondary_ports.workspace_manager import (
    FakeWorkspaceManager,
    WorkspaceManagerError,
)
from mb_workflow.b_core.d_domain_model.flow import StateName, StateNames, WorkflowChart
from mb_workflow.b_core.d_domain_model.workspace import (
    RepoId,
    WorkspaceStatus,
    WorkspaceStatuses,
    Worktree,
    WorktreeName,
    WorktreePath,
    Worktrees,
)
from mb_workflow.c_infrastructure.orca import ColumnLabel, ErrorMessage
from mb_workflow.c_infrastructure.workspace_board import (
    BoardError,
    Column,
    Columns,
    StateColumns,
    WorkspaceBoard,
)

REFUSAL = ErrorMessage(
    'Unknown workspace status "zzz". Available: status-8-2 (Tomorrow), in-progress (Grilling), '
    "status-9 (Speccing), status-5-2 (Implementing), status-8 (Me reviewing others), "
    "in-review (My QA), status-5 (Awaiting review), completed (Merging), status-6 (Merged)."
)


def board() -> Columns:
    return Columns.parse(REFUSAL).unwrap()


def state_of(status: WorkspaceStatus | None) -> StateName:
    return board().state_of(status, StateNames.initial_state(WorkflowChart))


def test_reads_the_id_to_label_table_from_the_columns_orca_names() -> None:
    assert board().label_of(WorkspaceStatus("status-5-2")) == ColumnLabel("Implementing")
    assert board().id_of(ColumnLabel("Me reviewing others")) == WorkspaceStatus("status-8")


def test_reads_every_column_orca_names() -> None:
    assert len(board().root) == 9


def test_a_refusal_naming_no_columns_is_a_clear_error() -> None:
    refusal = ErrorMessage("Unknown workspace status. Available: .")
    assert Columns.parse(refusal) == Err(BoardError(f"Orca named no board columns: {refusal.root}"))


def test_an_id_the_board_does_not_define_has_no_label() -> None:
    assert board().label_of(WorkspaceStatus("status-404")) is None


def test_every_state_the_chart_holds_has_a_board_column() -> None:
    assert StateNames(
        frozenset(pairing.state for pairing in StateColumns.of_chart().root)
    ) == StateNames.of_chart(WorkflowChart)


def test_a_column_id_resolves_to_the_state_its_label_stands_for() -> None:
    assert state_of(WorkspaceStatus("in-review")) == StateName("qa")


def test_a_column_outside_the_chart_reads_as_the_start_state() -> None:
    assert state_of(WorkspaceStatus("status-8")) == StateNames.initial_state(WorkflowChart)


def test_a_workspace_with_no_column_reads_as_the_start_state() -> None:
    assert state_of(None) == StateNames.initial_state(WorkflowChart)


def test_a_column_the_board_no_longer_defines_reads_as_the_start_state() -> None:
    assert state_of(WorkspaceStatus("status-404")) == StateNames.initial_state(WorkflowChart)


def test_a_state_maps_to_the_id_of_the_board_column_its_label_names() -> None:
    assert board().status_for(StateName("review")).unwrap() == WorkspaceStatus("status-5")


def test_a_state_the_board_has_no_column_for_is_a_clear_error() -> None:
    columns = Columns((Column(id=WorkspaceStatus("in-progress"), label=ColumnLabel("Grilling")),))
    unrecorded = columns.status_for(StateName("merged"))
    assert isinstance(unrecorded, Err)
    assert "defines no Merged column" in str(unrecorded.error)


def test_a_state_outside_the_chart_has_no_board_column() -> None:
    assert StateColumns.of_chart().label_of(StateName("Abandoned")) == Err(
        BoardError("Abandoned has no board column.")
    )


def standing_in(status: WorkspaceStatus | None) -> FakeWorkspaceManager:
    here = Worktree.bare(RepoId.fake(), WorktreePath.fake()).model_copy(update={"status": status})
    return FakeWorkspaceManager(
        Worktrees((here,)), here.path, WorkspaceStatuses(tuple(c.id for c in board().root))
    )


def board_over(
    manager: FakeWorkspaceManager, columns: Result[Columns, WorkspaceManagerError]
) -> WorkspaceBoard:
    return WorkspaceBoard(
        manager, lambda: columns, StateNames.initial_state(WorkflowChart), manager.current
    )


def test_the_board_reads_the_state_of_the_column_you_stand_in() -> None:
    qa = StateName("qa")
    manager = standing_in(WorkspaceStatus("in-review"))
    assert board_over(manager, Ok(board())).read() == Ok(qa)


def test_the_board_moves_the_worktree_you_stand_in_to_the_state_column() -> None:
    review_column = WorkspaceStatus("status-5")
    manager = standing_in(None)
    assert board_over(manager, Ok(board())).write(StateName("review")) == Ok(None)
    assert manager.current().unwrap().status == review_column


def test_unreadable_columns_leave_the_worktree_where_it_was() -> None:
    standing = WorkspaceStatus("in-review")
    manager = standing_in(standing)
    unread = Err(WorkspaceManagerError("Orca printed no columns."))
    store = board_over(manager, unread)
    assert store.read() == unread
    assert store.write(StateName("review")) == unread
    assert manager.current().unwrap().status == standing


def there() -> WorktreePath:
    return WorktreePath.fake().sibling(WorktreeName("there"))


def standing_beside(
    here: WorkspaceStatus, beside_status: WorkspaceStatus | None
) -> FakeWorkspaceManager:
    standing = Worktree.bare(RepoId.fake(), WorktreePath.fake()).model_copy(update={"status": here})
    beside = Worktree.bare(RepoId.fake(), there()).model_copy(update={"status": beside_status})
    return FakeWorkspaceManager(
        Worktrees((standing, beside)),
        standing.path,
        WorkspaceStatuses(tuple(c.id for c in board().root)),
    )


def test_the_board_at_a_worktree_reads_that_worktree_s_column() -> None:
    qa = StateName("qa")
    manager = standing_beside(WorkspaceStatus("status-5-2"), WorkspaceStatus("in-review"))
    assert board_over(manager, Ok(board())).at(there()).read() == Ok(qa)


def test_the_board_at_a_worktree_moves_that_worktree_and_not_the_one_you_stand_in() -> None:
    standing = WorkspaceStatus("status-5-2")
    review_column = WorkspaceStatus("status-5")
    manager = standing_beside(standing, None)
    assert board_over(manager, Ok(board())).at(there()).write(StateName("review")) == Ok(None)
    moved = manager.worktrees().unwrap().at(there())
    assert moved is not None
    assert moved.status == review_column
    assert manager.current().unwrap().status == standing


def test_the_board_at_a_path_with_no_worktree_is_a_clear_error() -> None:
    missing = WorktreePath.fake().sibling(WorktreeName("missing"))
    store = board_over(standing_in(None), Ok(board())).at(missing)
    assert store.read() == Err(WorkspaceManagerError(f"No worktree is at {missing.root}."))
