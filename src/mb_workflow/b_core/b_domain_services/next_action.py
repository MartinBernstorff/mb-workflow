from typing import TYPE_CHECKING

from mb_workflow.b_core.d_domain_model.flow import (
    FlowError,
    StateName,
    StateNames,
    WorkflowChart,
    WorkState,
)
from mb_workflow.b_core.d_domain_model.issue import StatusName, StatusNames

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.flow import NextAction


def state_of(chart: type[WorkflowChart], status: StatusName) -> StateName:
    if StatusNames.closed().matching(status) is not None:
        raise FlowError(f"The issue is {status.root}, so there is no work left in it.")
    if status.names(StatusName("Backlog")).root:
        return StateNames.initial_state(chart)
    for state in StateNames.of_chart(chart).root:
        if status.names(StatusName(state.root)).root:
            return state
    raise FlowError(f"{status.root} is no state of the chart.")


def next_action(chart: type[WorkflowChart], state: StateName) -> NextAction:
    for candidate in chart.states:
        if isinstance(candidate, WorkState) and StateName(candidate.name) == state:
            return candidate.action
    raise FlowError(f"{state.root} is no state of the chart.")
