from typing import TYPE_CHECKING

from mb_workflow.b_core.b_domain_services.flow_label_check import require_flow_labels
from mb_workflow.b_core.d_domain_model.flow import Edges, EventName, StateName, WorkflowChart
from mb_workflow.d_lib.models import Value

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier


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
    event: EventName,
    force: Force,
) -> StateName:
    edges = Edges.of_chart(chart)
    target = edges.target_of(event) if force.root else edges.target_from(store.read(), event)
    require_flow_labels(tracker, wanted)
    tracker.set_labels(issue, wanted.relabelled(tracker.read_issue(issue).labels, target))
    store.write(target)
    return target
