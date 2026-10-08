from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from mb_workflow.b_core.d_domain_model.flow import ReviewChart, StateName, StateNames
from mb_workflow.b_core.d_domain_model.workspace import WorkspaceStatus, WorkspaceStatuses
from mb_workflow.d_lib.models import Model

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManagerError


# The board columns of the review chart's states, looked up by label so no column id is hard-coded.
class ReviewColumns(Model):
    start: WorkspaceStatus
    held: WorkspaceStatuses

    @staticmethod
    def fake() -> ReviewColumns:
        return ReviewColumns(start=WorkspaceStatus.fake(), held=WorkspaceStatuses.fake())

    # The state I finish the review in; finishing it removes the worktree.
    @staticmethod
    def finishing_state() -> StateName:
        return StateName(ReviewChart.reviewing.name)

    @staticmethod
    def on_board(board: WorkspaceStatusStore) -> Result[ReviewColumns, WorkspaceManagerError]:
        held: list[WorkspaceStatus] = []
        for state in ReviewChart.states:
            match board.status_for(StateName(state.name)):
                case Ok(status):
                    held.append(status)
                case Err() as unmapped:
                    return unmapped
        match board.status_for(StateNames.initial_state(ReviewChart)):
            case Ok(start):
                return Ok(ReviewColumns(start=start, held=WorkspaceStatuses(tuple(held))))
            case Err() as unmapped:
                return unmapped
