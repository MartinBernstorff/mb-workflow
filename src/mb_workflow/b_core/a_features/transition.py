from typing import TYPE_CHECKING

from mb_workflow.b_core.b_domain_services.flow_transition import Force, transitioned
from mb_workflow.b_core.d_domain_model.flow import EventName, StateName, StateNames, WorkflowChart
from mb_workflow.c_infrastructure.board import WorkspaceBoard
from mb_workflow.c_infrastructure.orca import Orca

if TYPE_CHECKING:
    from mb_workflow.c_infrastructure.shell import Shell


def transition(shell: Shell, event: EventName, force: Force) -> StateName:
    board = WorkspaceBoard.of_orca(Orca(shell), StateNames.start(WorkflowChart))
    return transitioned(WorkflowChart, board, event, force)
