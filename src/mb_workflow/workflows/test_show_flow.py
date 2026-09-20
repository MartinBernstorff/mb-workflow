from typing import TYPE_CHECKING

from mb_workflow.flow import FlowStatus, StateName
from mb_workflow.shell import ExitCode
from mb_workflow.status import FakeStatusStore
from mb_workflow.workflows.show_flow import AsJson, StatusReport, shown

if TYPE_CHECKING:
    import pytest


def test_prints_the_current_state_and_the_events_legal_from_it() -> None:
    status = FlowStatus.of(StateName("Merging"))
    assert StatusReport.of(status, AsJson(False)) == StatusReport("Merging\n  merged\n")


def test_a_final_state_prints_on_its_own() -> None:
    status = FlowStatus.of(StateName("Merged"))
    assert StatusReport.of(status, AsJson(False)) == StatusReport("Merged\n")


def test_json_emits_the_same_state_and_events_for_scripting() -> None:
    status = FlowStatus.of(StateName("Merging"))
    assert StatusReport.of(status, AsJson(True)) == StatusReport(
        '{"state":"Merging","events":["merged"]}\n'
    )


def test_reads_the_state_from_the_status_store(capsys: pytest.CaptureFixture[str]) -> None:
    assert shown(FakeStatusStore(StateName("Merging")), AsJson(False)) == ExitCode(0)
    assert capsys.readouterr().out == "Merging\n  merged\n"
