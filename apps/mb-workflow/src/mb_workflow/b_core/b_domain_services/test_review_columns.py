from assertions import Assert
from safe_result import Err

from mb_workflow.b_core.b_domain_services.review_columns import ReviewColumns
from mb_workflow.b_core.c_secondary_ports.status import FakeStatusStore, UnreachableStatusStore
from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManagerError
from mb_workflow.b_core.d_domain_model.flow import StateName


def board() -> FakeStatusStore:
    return FakeStatusStore(StateName.fake())


def test_a_review_starts_in_the_agent_reviewing_column() -> None:
    agent_reviewing = board().status_for(StateName("agent-reviewing")).unwrap()
    Assert.that(ReviewColumns.on_board(board()).unwrap().start).matches(agent_reviewing)


def test_a_review_is_held_in_both_review_columns() -> None:
    agent_reviewing = board().status_for(StateName("agent-reviewing")).unwrap()
    reviewing = board().status_for(StateName("reviewing")).unwrap()
    columns = ReviewColumns.on_board(board()).unwrap()
    Assert.that(set(columns.held.root)).matches({agent_reviewing, reviewing})


def test_an_unreachable_board_names_no_columns() -> None:
    columns = ReviewColumns.on_board(UnreachableStatusStore())
    assert isinstance(columns, Err)
    assert isinstance(columns.error, WorkspaceManagerError)
