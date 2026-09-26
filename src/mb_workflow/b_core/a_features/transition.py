from typing import TYPE_CHECKING

from mb_workflow.b_core.b_domain_services import flow_transition
from mb_workflow.b_core.d_domain_model.flow import EventName, StateName, WorkflowChart

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore


def transition(
    store: WorkspaceStatusStore, event: EventName, force: flow_transition.Force
) -> StateName:
    return flow_transition.transition(WorkflowChart, store, event, force)
