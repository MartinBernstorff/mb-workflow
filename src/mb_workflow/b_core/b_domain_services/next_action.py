from typing import TYPE_CHECKING

from mb_workflow.b_core.d_domain_model.flow import (
    Finished,
    FlowError,
    StateName,
    WorkflowChart,
    WorkState,
)
from mb_workflow.b_core.d_domain_model.flow_labels import state_of

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.flow import NextAction
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.issue import Issue


def next_action(chart: type[WorkflowChart], state: StateName) -> NextAction:
    for candidate in chart.states:
        if isinstance(candidate, WorkState) and StateName(candidate.name) == state:
            return candidate.action
    raise FlowError(f"{state.root} is no state of the chart.")


class TicketState:
    # Checked before a ticket is taken, so one outside the flow or with no work left is never claimed.
    @staticmethod
    def state_with_work_left(
        chart: type[WorkflowChart], flow_labels: FlowLabels, issue: Issue
    ) -> StateName:
        state = state_of(chart, flow_labels, issue.grouped)
        if state is None:
            raise FlowError(
                f"{issue.identifier.root} carries no flow label, so it is not in the flow."
            )
        if isinstance(next_action(chart, state), Finished):
            raise FlowError(f"The ticket is {state.root}, so there is no work left in it.")
        return state
