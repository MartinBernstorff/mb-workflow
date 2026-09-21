import logging
import sys
from subprocess import CalledProcessError
from typing import TYPE_CHECKING

from mb_workflow.a_presentation.console import ExitCode
from mb_workflow.b_core.flow import FlowStatus, StateNames, WorkflowChart
from mb_workflow.c_infrastructure.board import Board, BoardError
from mb_workflow.c_infrastructure.orca import Orca, OrcaError
from mb_workflow.d_lib.models import Value

if TYPE_CHECKING:
    from mb_workflow.b_core.status import StatusStore
    from mb_workflow.c_infrastructure.shell import Shell

logger = logging.getLogger(__name__)


class AsJson(Value[bool]):
    @staticmethod
    def fake() -> AsJson:
        return AsJson(False)


class StatusReport(Value[str]):
    @staticmethod
    def fake() -> StatusReport:
        return StatusReport.of(FlowStatus.fake(), AsJson.fake())

    @staticmethod
    def of(status: FlowStatus, as_json: AsJson) -> StatusReport:
        if as_json.root:
            return StatusReport(f"{status.model_dump_json()}\n")
        legal = "".join(f"  {event.root}\n" for event in status.events.root)
        return StatusReport(f"{status.state.root}\n{legal}")


def show_flow(shell: Shell, as_json: AsJson) -> ExitCode:
    try:
        return shown(
            WorkflowChart, Board.of_orca(Orca(shell), StateNames.start(WorkflowChart)), as_json
        )
    except FileNotFoundError as error:
        logger.error("%s is not installed or not on PATH.", error.filename)
        return ExitCode(1)
    except (BoardError, CalledProcessError, OSError, OrcaError, ValueError) as error:
        logger.error("%s", error)
        return ExitCode(1)


def shown(chart: type[WorkflowChart], store: StatusStore, as_json: AsJson) -> ExitCode:
    _ = sys.stdout.write(StatusReport.of(FlowStatus.of(chart, store.read()), as_json).root)
    return ExitCode(0)
