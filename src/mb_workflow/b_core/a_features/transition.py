import logging
from subprocess import CalledProcessError
from typing import TYPE_CHECKING

from mb_workflow.a_presentation.console import ExitCode
from mb_workflow.b_core.b_domain_services.flow_transition import Force, transitioned
from mb_workflow.b_core.d_domain_model.flow import EventName, FlowError, StateNames, WorkflowChart
from mb_workflow.c_infrastructure.board import Board, BoardError
from mb_workflow.c_infrastructure.orca import Orca, OrcaError

if TYPE_CHECKING:
    from mb_workflow.c_infrastructure.shell import Shell

logger = logging.getLogger(__name__)


def transition(shell: Shell, event: EventName, force: Force) -> ExitCode:
    try:
        board = Board.of_orca(Orca(shell), StateNames.start(WorkflowChart))
        return transitioned(WorkflowChart, board, event, force)
    except FileNotFoundError as error:
        logger.error("%s is not installed or not on PATH.", error.filename)
        return ExitCode(1)
    except (BoardError, CalledProcessError, FlowError, OSError, OrcaError, ValueError) as error:
        logger.error("%s", error)
        return ExitCode(1)
