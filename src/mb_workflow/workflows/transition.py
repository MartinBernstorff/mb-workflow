import logging
from subprocess import CalledProcessError
from typing import TYPE_CHECKING

from mb_workflow.flow import Edges, EventName, FlowError
from mb_workflow.models import Value
from mb_workflow.shell import ExitCode, Shell
from mb_workflow.workspace.board import Board, BoardError
from mb_workflow.workspace.orca import Orca, OrcaError

if TYPE_CHECKING:
    from mb_workflow.status import StatusStore

logger = logging.getLogger(__name__)


class Force(Value[bool]):
    @staticmethod
    def fake() -> Force:
        return Force(False)


def transition(shell: Shell, event: EventName, force: Force) -> ExitCode:
    try:
        return transitioned(Board.of_orca(Orca(shell)), event, force)
    except FileNotFoundError as error:
        logger.error("%s is not installed or not on PATH.", error.filename)
        return ExitCode(1)
    except (BoardError, CalledProcessError, FlowError, OSError, OrcaError, ValueError) as error:
        logger.error("%s", error)
        return ExitCode(1)


def transitioned(store: StatusStore, event: EventName, force: Force) -> ExitCode:
    edges = Edges.of_chart()
    target = edges.target_of(event) if force.root else edges.target_from(store.read(), event)
    store.write(target)
    logger.info("Moved to %s.", target.root)
    return ExitCode(0)
