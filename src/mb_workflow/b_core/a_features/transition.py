from typing import TYPE_CHECKING

from mb_workflow.b_core.b_domain_services import flow_transition
from mb_workflow.b_core.d_domain_model.flow import EventName, StateName, StateNames, WorkflowChart
from mb_workflow.c_infrastructure.orca import Orca
from mb_workflow.c_infrastructure.workspace_board import WorkspaceBoard

if TYPE_CHECKING:
    from mb_workflow.c_infrastructure.shell import Shell


def transition(shell: Shell, event: EventName, force: flow_transition.Force) -> StateName:
    board = WorkspaceBoard.of_orca(Orca(shell), StateNames.initial_state(WorkflowChart))
    return flow_transition.transition(WorkflowChart, board, event, force)
