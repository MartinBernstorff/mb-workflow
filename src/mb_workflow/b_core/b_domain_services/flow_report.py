from typing import TYPE_CHECKING

from mb_workflow.b_core.d_domain_model.flow import FlowStatus, WorkflowChart
from mb_workflow.d_lib.models import Value

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.status import StatusStore


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


def status_report(chart: type[WorkflowChart], store: StatusStore, as_json: AsJson) -> StatusReport:
    return StatusReport.of(FlowStatus.of(chart, store.read()), as_json)
