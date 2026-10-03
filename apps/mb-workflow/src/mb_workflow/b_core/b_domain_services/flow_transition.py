from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from mb_workflow.b_core.b_domain_services.flow_label_check import FlowLabelCheck
from mb_workflow.b_core.d_domain_model.flow import Edges, EventName, StateName, WorkflowChart
from mb_workflow.b_core.d_domain_model.issue import IssueUpdate
from mb_workflow.d_lib.models import Value

if TYPE_CHECKING:
    from mb_workflow.b_core.b_domain_services.flow_label_check import MissingFlowLabelsError
    from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
        TicketTracker,
        TicketTrackerError,
    )
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
    from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses


class Force(Value[bool]):
    @staticmethod
    def fake() -> Force:
        return Force(False)


def transition(
    *,
    chart: type[WorkflowChart],
    store: WorkspaceStatusStore,
    tracker: TicketTracker,
    issue: IssueIdentifier,
    wanted: FlowLabels,
    statuses: TicketStatuses,
    event: EventName,
    force: Force,
) -> Result[StateName, TicketTrackerError | MissingFlowLabelsError]:
    edges = Edges.of_chart(chart)
    target = edges.target_of(event) if force.root else edges.target_from(store.read(), event)
    put = put_in_state(tracker, issue, wanted, statuses, target)
    if isinstance(put, Err):
        return put
    store.write(target)
    return Ok(target)


def put_in_state(
    tracker: TicketTracker,
    issue: IssueIdentifier,
    wanted: FlowLabels,
    statuses: TicketStatuses,
    state: StateName,
) -> Result[None, TicketTrackerError | MissingFlowLabelsError]:
    team = tracker.team_of(issue)
    if isinstance(team, Err):
        return team
    checked = FlowLabelCheck.require(tracker, wanted, team.value)
    if isinstance(checked, Err):
        return checked
    held = tracker.read_issue(issue)
    if isinstance(held, Err):
        return held
    labels = wanted.relabelled(held.value.labels, state)
    tracker.update_issue(
        issue,
        IssueUpdate.nothing().model_copy(update={"labels": labels, "status": statuses.of(state)}),
    )
    return Ok(None)
