from typing import TYPE_CHECKING

from mb_workflow.b_core.d_domain_model.flow import Edges, EventName, StateName, WorkflowChart
from mb_workflow.d_lib.models import Value

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore


class Force(Value[bool]):
    @staticmethod
    def fake() -> Force:
        return Force(False)


def transitioned(
    chart: type[WorkflowChart], store: WorkspaceStatusStore, event: EventName, force: Force
) -> StateName:
    edges = Edges.of_chart(chart)
    target = edges.target_of(event) if force.root else edges.target_from(store.read(), event)
    store.write(target)
    return target
