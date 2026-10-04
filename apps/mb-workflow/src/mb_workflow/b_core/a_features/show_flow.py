from typing import TYPE_CHECKING

from mb_workflow.b_core.b_domain_services.flow_report import AsJson, StatusReport, status_report
from mb_workflow.b_core.d_domain_model.flow import WorkflowChart

if TYPE_CHECKING:
    from safe_result import Result

    from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManagerError


def show_flow(
    store: WorkspaceStatusStore, as_json: AsJson
) -> Result[StatusReport, WorkspaceManagerError]:
    return status_report(WorkflowChart, store, as_json)
