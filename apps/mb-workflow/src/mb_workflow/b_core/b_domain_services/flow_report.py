from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from mb_workflow.b_core.d_domain_model.flow import Chart, FlowStatus
from mb_workflow.d_lib.models import Value

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManagerError


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

    @staticmethod
    def of_store(
        chart: Chart, store: WorkspaceStatusStore, as_json: AsJson
    ) -> Result[StatusReport, WorkspaceManagerError]:
        match store.read():
            case Ok(state):
                return Ok(StatusReport.of(FlowStatus.of(chart, state), as_json))
            case Err() as unread:
                return unread
