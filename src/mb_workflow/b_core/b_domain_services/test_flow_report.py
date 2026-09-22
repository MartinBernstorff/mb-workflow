from mb_workflow.b_core.b_domain_services.flow_report import AsJson, StatusReport, status_report
from mb_workflow.b_core.c_secondary_ports.status import FakeStatusStore
from mb_workflow.b_core.d_domain_model.flow import FlowStatus, StateName, WorkflowChart


def test_prints_the_current_state_and_the_events_legal_from_it() -> None:
    status = FlowStatus.of(WorkflowChart, StateName("Merging"))
    assert StatusReport.of(status, AsJson(False)) == StatusReport("Merging\n  merged\n")


def test_a_final_state_prints_on_its_own() -> None:
    status = FlowStatus.of(WorkflowChart, StateName("Merged"))
    assert StatusReport.of(status, AsJson(False)) == StatusReport("Merged\n")


def test_json_emits_the_same_state_and_events_for_scripting() -> None:
    status = FlowStatus.of(WorkflowChart, StateName("Merging"))
    assert StatusReport.of(status, AsJson(True)) == StatusReport(
        '{"state":"Merging","events":["merged"]}\n'
    )


def test_reads_the_state_from_the_status_store() -> None:
    store = FakeStatusStore(StateName("Merging"))
    assert status_report(WorkflowChart, store, AsJson(False)) == StatusReport("Merging\n  merged\n")
