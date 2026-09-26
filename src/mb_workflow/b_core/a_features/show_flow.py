from typing import TYPE_CHECKING

from mb_workflow.b_core.b_domain_services.flow_report import AsJson, StatusReport, status_report
from mb_workflow.b_core.d_domain_model.flow import StateNames, WorkflowChart
from mb_workflow.c_infrastructure.orca import Orca
from mb_workflow.c_infrastructure.workspace_board import WorkspaceBoard

if TYPE_CHECKING:
    from mb_workflow.c_infrastructure.shell import Shell


def show_flow(shell: Shell, as_json: AsJson) -> StatusReport:
    board = WorkspaceBoard.of_orca(Orca(shell), StateNames.initial_state(WorkflowChart))
    return status_report(WorkflowChart, board, as_json)
