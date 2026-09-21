from typing import TYPE_CHECKING

from mb_workflow.a_presentation.console import ExitCode
from mb_workflow.b_core.features.show_flow import AsJson, StatusReport, shown
from mb_workflow.b_core.flow import FlowStatus, StateName, WorkflowChart
from mb_workflow.b_core.status import FakeStatusStore

if TYPE_CHECKING:
    import pytest


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


def test_reads_the_state_from_the_status_store(capsys: pytest.CaptureFixture[str]) -> None:
    assert shown(WorkflowChart, FakeStatusStore(StateName("Merging")), AsJson(False)) == ExitCode(0)
    assert capsys.readouterr().out == "Merging\n  merged\n"
