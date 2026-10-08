import pytest
from assertions import Assert
from safe_result import Err, Ok, Result

from mb_workflow.b_core.c_secondary_ports.workspace_manager import (
    FakeWorkspaceManager,
    WorkspaceManagerError,
)
from mb_workflow.b_core.d_domain_model.flow import ReviewChart, StateName, StateNames, WorkflowChart
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
    "status-9 (Speccing), status-5-2 (Implementing), status-10 (Agent reviewing), "
    "status-8 (Me reviewing others), "
    "in-review (My QA), status-5 (Awaiting review), completed (Merging), status-6 (Merged)."
)


def board() -> Columns:
    return Columns.parse(REFUSAL).unwrap()


def state_of(status: WorkspaceStatus | None) -> StateName:
    return board().state_of(status, StateNames.initial_state(WorkflowChart))


def test_reads_the_id_to_label_table_from_the_columns_orca_names() -> None:
    implementing = ColumnLabel("Implementing")
    reviewing_others = WorkspaceStatus("status-8")
    Assert.that(board().label_of(WorkspaceStatus("status-5-2"))).matches(implementing)
    Assert.that(board().id_of(ColumnLabel("Me reviewing others"))).matches(reviewing_others)


def test_reads_every_column_orca_names() -> None:
    column_count = 10
    Assert.that(board().root).has_length(column_count)


def test_a_refusal_naming_no_columns_is_a_clear_error() -> None:
    refusal = ErrorMessage("Unknown workspace status. Available: .")
    Assert.that(Columns.parse(refusal)).matches(
        Err(BoardError(f"Orca named no board columns: {refusal.root}"))
    )


def test_an_id_the_board_does_not_define_has_no_label() -> None:
    Assert.that(board().label_of(WorkspaceStatus("status-404"))).matches(None)


def test_every_state_either_chart_holds_has_a_board_column() -> None:
    Assert.that(
        StateNames(frozenset(pairing.state for pairing in StateColumns.of_charts().root))
    ).matches(
        StateNames(StateNames.of_chart(WorkflowChart).root | StateNames.of_chart(ReviewChart).root)
    )


def test_a_column_id_resolves_to_the_state_its_label_stands_for() -> None:
    qa = StateName("qa")
    Assert.that(state_of(WorkspaceStatus("in-review"))).matches(qa)


def test_agent_reviewing_is_recorded_in_the_agent_reviewing_column() -> None:
    agent_reviewing_column = WorkspaceStatus("status-10")
    Assert.that(board().status_for(StateName("agent-reviewing")).unwrap()).matches(
        agent_reviewing_column
    )


def test_a_worktree_in_me_reviewing_others_reads_as_reviewing() -> None:
    reviewing = StateName("reviewing")
    Assert.that(state_of(WorkspaceStatus("status-8"))).matches(reviewing)


def test_reviewing_is_recorded_in_the_me_reviewing_others_column() -> None:
    reviewing_others = WorkspaceStatus("status-8")
    manager = standing_in(WorkspaceStatus("status-10"))
    Assert.that(board_over(manager, Ok(board())).write(StateName("reviewing"))).matches(Ok(None))
    Assert.that(manager.current().unwrap().status).matches(reviewing_others)


def test_a_workspace_with_no_column_reads_as_the_start_state() -> None:
    Assert.that(state_of(None)).matches(StateNames.initial_state(WorkflowChart))


def test_a_column_the_board_no_longer_defines_reads_as_the_start_state() -> None:
    Assert.that(state_of(WorkspaceStatus("status-404"))).matches(
        StateNames.initial_state(WorkflowChart)
    )


def test_a_state_maps_to_the_id_of_the_board_column_its_label_names() -> None:
    review_column = WorkspaceStatus("status-5")
    Assert.that(board().status_for(StateName("review")).unwrap()).matches(review_column)


def test_a_state_the_board_has_no_column_for_is_a_clear_error() -> None:
    columns = Columns((Column(id=WorkspaceStatus("in-progress"), label=ColumnLabel("Grilling")),))
    unrecorded = columns.status_for(StateName("merged"))
    error = Assert.that(unrecorded).is_err(BoardError)
    Assert.that(str(error)).contains("defines no Merged column")


def test_a_state_outside_the_chart_has_no_board_column() -> None:
    Assert.that(StateColumns.of_charts().label_of(StateName("Abandoned"))).matches(
        Err(BoardError("Abandoned has no board column."))
    )


def standing_in(status: WorkspaceStatus | None) -> FakeWorkspaceManager:
    return standing_in_worktree(
        Worktree.bare(RepoId.fake(), WorktreePath.fake()).model_copy(update={"status": status})
    )


def standing_in_worktree(here: Worktree) -> FakeWorkspaceManager:
    return FakeWorkspaceManager(
        Worktrees((here,)), here.path, WorkspaceStatuses(tuple(c.id for c in board().root))
    )


def board_over(
    manager: FakeWorkspaceManager, columns: Result[Columns, WorkspaceManagerError]
) -> WorkspaceBoard:
    return WorkspaceBoard(manager, lambda: columns, manager.current)


def test_the_board_reads_the_state_of_the_column_you_stand_in() -> None:
    qa = StateName("qa")
    manager = standing_in(WorkspaceStatus("in-review"))
    Assert.that(board_over(manager, Ok(board())).read()).matches(Ok(qa))


def test_the_board_moves_the_worktree_you_stand_in_to_the_state_column() -> None:
    review_column = WorkspaceStatus("status-5")
    manager = standing_in(None)
    Assert.that(board_over(manager, Ok(board())).write(StateName("review"))).matches(Ok(None))
    Assert.that(manager.current().unwrap().status).matches(review_column)


def test_unreadable_columns_leave_the_worktree_where_it_was() -> None:
    standing = WorkspaceStatus("in-review")
    manager = standing_in(standing)
    unread = Err(WorkspaceManagerError("Orca printed no columns."))
    store = board_over(manager, unread)
    Assert.that(store.read()).matches(unread)
    Assert.that(store.write(StateName("review"))).matches(unread)
    Assert.that(manager.current().unwrap().status).matches(standing)


def test_the_board_at_a_worktree_reads_that_worktree_s_column() -> None:
    qa = StateName("qa")
    there = Worktree.fake().model_copy(update={"status": WorkspaceStatus("in-review")})
    manager = standing_in(WorkspaceStatus("status-5-2"))
    Assert.that(board_over(manager, Ok(board())).at(there).read()).matches(Ok(qa))


def test_the_board_at_a_worktree_moves_that_worktree_and_not_the_one_you_stand_in() -> None:
    standing = WorkspaceStatus("status-5-2")
    review_column = WorkspaceStatus("status-5")
    here = Worktree.bare(RepoId.fake(), WorktreePath.fake()).model_copy(update={"status": standing})
    there = Worktree.bare(RepoId.fake(), WorktreePath.fake().sibling(WorktreeName("there")))
    manager = FakeWorkspaceManager(
        Worktrees((here, there)), here.path, WorkspaceStatuses(tuple(c.id for c in board().root))
    )
    Assert.that(board_over(manager, Ok(board())).at(there).write(StateName("review"))).matches(
        Ok(None)
    )
    moved = Assert.that(manager.worktrees().unwrap().at(there.path)).exists()
    Assert.that(moved.status).matches(review_column)
    Assert.that(manager.current().unwrap().status).matches(standing)


def reviewing_teammate_pr(status: WorkspaceStatus | None) -> Worktree:
    return Worktree.fake().model_copy(update={"issue": None, "status": status})


@pytest.mark.parametrize("status", [None, WorkspaceStatus("status-404")])
def test_a_review_worktree_outside_any_known_column_reads_as_the_review_start_state(
    status: WorkspaceStatus | None,
) -> None:
    manager = standing_in_worktree(reviewing_teammate_pr(status))
    Assert.that(board_over(manager, Ok(board())).read()).matches(
        Ok(StateNames.initial_state(ReviewChart))
    )


@pytest.mark.parametrize("status", [None, WorkspaceStatus("status-404")])
def test_a_worktree_for_my_own_ticket_outside_any_known_column_reads_as_the_workflow_start_state(
    status: WorkspaceStatus | None,
) -> None:
    manager = standing_in_worktree(Worktree.fake().model_copy(update={"status": status}))
    Assert.that(board_over(manager, Ok(board())).read()).matches(
        Ok(StateNames.initial_state(WorkflowChart))
    )
