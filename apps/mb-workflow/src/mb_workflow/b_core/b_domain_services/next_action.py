from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from mb_workflow.b_core.d_domain_model.flow import (
    Finished,
    FlowError,
    StateName,
    WorkflowChart,
    WorkState,
)

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.flow import NextAction
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.issue import Issue


class TicketState:
    @staticmethod
    def next_action(chart: type[WorkflowChart], state: StateName) -> Result[NextAction, FlowError]:
        for candidate in chart.states:
            if isinstance(candidate, WorkState) and StateName(candidate.name) == state:
                return Ok(candidate.action)
        return Err(FlowError(f"{state.root} is no state of the chart."))

    @staticmethod
    def state_with_work_left(
        chart: type[WorkflowChart], flow_labels: FlowLabels, issue: Issue
    ) -> Result[StateName, FlowError]:
        match flow_labels.state_of(chart, issue.grouped):
            case Err() as unresolved:
                return unresolved
            case Ok(state):
                if state is None:
                    return Err(
                        FlowError(
                            f"{issue.identifier.root} carries no flow label, so it is not in the flow."
                        )
                    )
                return TicketState._with_work_left(chart, state)

    @staticmethod
    def _with_work_left(
        chart: type[WorkflowChart], state: StateName
    ) -> Result[StateName, FlowError]:
        match TicketState.next_action(chart, state):
            case Err() as unknown:
                return unknown
            case Ok(Finished()):
                return Err(
                    FlowError(f"The ticket is {state.root}, so there is no work left in it.")
                )
            case Ok():
                return Ok(state)
