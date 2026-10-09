from assertions import Assert
from safe_result import Err, Ok

from mb_workflow.b_core.b_domain_services.flow_report import AsJson, StatusReport
from mb_workflow.b_core.c_secondary_ports.status import FakeStatusStore, UnreachableStatusStore
from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManagerError
from mb_workflow.b_core.d_domain_model.flow import FlowStatus, StateName, WorkflowChart


def test_prints_the_current_state_and_the_events_legal_from_it() -> None:
    status = FlowStatus.of(WorkflowChart, StateName("merging"))
    Assert.that(StatusReport.of(status, AsJson(False))).matches(
        StatusReport("merging\n  merged\n  qa\n")
    )


def test_a_final_state_prints_on_its_own() -> None:
    status = FlowStatus.of(WorkflowChart, StateName("merged"))
    Assert.that(StatusReport.of(status, AsJson(False))).matches(StatusReport("merged\n"))


def test_json_emits_the_same_state_and_events_for_scripting() -> None:
    status = FlowStatus.of(WorkflowChart, StateName("merging"))
    Assert.that(StatusReport.of(status, AsJson(True))).matches(
        StatusReport('{"state":"merging","events":["merged","qa"]}\n')
    )


def test_reads_the_state_from_the_status_store() -> None:
    store = FakeStatusStore(StateName("merging"))
    Assert.that(StatusReport.of_store(WorkflowChart, store, AsJson(False))).matches(
        Ok(StatusReport("merging\n  merged\n  qa\n"))
    )


def test_an_unreachable_store_reports_no_state() -> None:
    reported = StatusReport.of_store(WorkflowChart, UnreachableStatusStore(), AsJson(False))
    Assert.that(reported).matches(Err(WorkspaceManagerError("The workspace board is unreachable.")))
