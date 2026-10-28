from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from mb_workflow.b_core.d_domain_model.flow import Chart, DescribedStates, FlowStatus
from mb_workflow.d_lib.models import Value

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManagerError
    from mb_workflow.b_core.d_domain_model.flow import StateDescription, StateName


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
        here = StatusReport.of_state(status.state, status.description)
        legal = "".join(
            f"  {option.event.root} -> {StatusReport.of_state(option.target, option.description).root}\n"
            for option in status.events
        )
        return StatusReport(f"{here.root}\n{legal}")

    # A state followed by its description, which tells an agent whether the ticket belongs there.
    @staticmethod
    def of_state(state: StateName, description: StateDescription | None) -> StatusReport:
        if description is None:
            return StatusReport(state.root)
        return StatusReport(f"{state.root}: {description.root}")

    @staticmethod
    def of_store(
        chart: Chart, store: WorkspaceStatusStore, as_json: AsJson
    ) -> Result[StatusReport, WorkspaceManagerError]:
        match store.read():
            case Ok(state):
                return Ok(StatusReport.of(FlowStatus.of(chart, state), as_json))
            case Err() as unread:
                return unread


class StatesReport(Value[str]):
    @staticmethod
    def fake() -> StatesReport:
        return StatesReport.of(DescribedStates.fake(), AsJson.fake())

    @staticmethod
    def of(states: DescribedStates, as_json: AsJson) -> StatesReport:
        if as_json.root:
            return StatesReport(f"{states.model_dump_json()}\n")
        return StatesReport(
            "".join(
                f"{StatusReport.of_state(held.state, held.description).root}\n"
                for held in states.root
            )
        )
