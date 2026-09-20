import logging
import sys
from subprocess import CalledProcessError
from typing import TYPE_CHECKING

from mb_workflow.flow import FlowStatus
from mb_workflow.models import Value
from mb_workflow.shell import ExitCode, Shell
from mb_workflow.workspace.board import Board, BoardError
from mb_workflow.workspace.orca import Orca, OrcaError

if TYPE_CHECKING:
    from mb_workflow.status import StatusStore

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
        return shown(Board.of_orca(Orca(shell)), as_json)
    except FileNotFoundError as error:
        logger.error("%s is not installed or not on PATH.", error.filename)
        return ExitCode(1)
    except (BoardError, CalledProcessError, OSError, OrcaError, ValueError) as error:
        logger.error("%s", error)
        return ExitCode(1)


def shown(store: StatusStore, as_json: AsJson) -> ExitCode:
    _ = sys.stdout.write(StatusReport.of(FlowStatus.of(store.read()), as_json).root)
    return ExitCode(0)
