from typing import TYPE_CHECKING

from safe_result import Err, Ok

from mb_workflow.b_core.a_features.transition import WorktreeTransition
from mb_workflow.b_core.b_domain_services.flow_report import AsJson, StatusReport

if TYPE_CHECKING:
    from collections.abc import Callable

    from safe_result import Result

    from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import (
        WorkspaceManager,
        WorkspaceManagerError,
    )
    from mb_workflow.b_core.d_domain_model.workspace import Worktree


# The worktree you stand in follows the chart of its kind, so a review lists the review's events.
class FlowShow:
    @staticmethod
    def show_flow(
        manager: WorkspaceManager,
        board_at: Callable[[Worktree], WorkspaceStatusStore],
        as_json: AsJson,
    ) -> Result[StatusReport, WorkspaceManagerError]:
        match manager.current():
            case Ok(here):
                return StatusReport.of_store(
                    WorktreeTransition.chart_of(here), board_at(here), as_json
                )
            case Err() as unlocated:
                return unlocated
