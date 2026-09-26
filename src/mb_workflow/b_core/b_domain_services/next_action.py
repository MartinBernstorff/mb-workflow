from typing import TYPE_CHECKING

from mb_workflow.b_core.d_domain_model.flow import FlowError, StateName, WorkflowChart, WorkState

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.flow import NextAction


def next_action(chart: type[WorkflowChart], state: StateName) -> NextAction:
    for candidate in chart.states:
        if isinstance(candidate, WorkState) and StateName(candidate.name) == state:
            return candidate.action
    raise FlowError(f"{state.root} is no state of the chart.")
