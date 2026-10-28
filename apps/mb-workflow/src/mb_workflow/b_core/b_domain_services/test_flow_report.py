from assertions import Assert
from safe_result import Err, Ok

from mb_workflow.b_core.b_domain_services.flow_report import AsJson, StatesReport, StatusReport
from mb_workflow.b_core.c_secondary_ports.status import FakeStatusStore, UnreachableStatusStore
from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManagerError
from mb_workflow.b_core.d_domain_model.flow import (
    DescribedState,
    DescribedStates,
    EventName,
    EventOption,
    FlowStatus,
    StateDescription,
    StateName,
    WorkflowChart,
)


def merging_status() -> FlowStatus:
    return FlowStatus(
        state=StateName("merging"),
        description=StateDescription("Approved."),
        events=(
            EventOption(
                event=EventName("merged"),
                target=StateName("merged"),
                description=StateDescription("Done."),
            ),
            EventOption(
                event=EventName("qa"), target=StateName("qa"), description=StateDescription("Test.")
            ),
        ),
    )


def test_prints_the_current_state_and_the_events_legal_from_it_with_descriptions() -> None:
    report = StatusReport("merging: Approved.\n  merged -> merged: Done.\n  qa -> qa: Test.\n")
    Assert.that(StatusReport.of(merging_status(), AsJson(False))).matches(report)


def test_a_final_state_prints_on_its_own() -> None:
    status = merging_status().model_copy(update={"events": ()})
    Assert.that(StatusReport.of(status, AsJson(False))).matches(
        StatusReport("merging: Approved.\n")
    )


def test_an_undescribed_state_prints_its_name_alone() -> None:
    outside = StateName("Marinating")
    status = FlowStatus(state=outside, description=None, events=())
    Assert.that(StatusReport.of(status, AsJson(False))).matches(StatusReport("Marinating\n"))


def test_json_emits_the_same_state_events_and_descriptions_for_scripting() -> None:
    status = merging_status().model_copy(update={"events": merging_status().events[1:]})
    report = StatusReport(
        '{"state":"merging","description":"Approved.",'
        '"events":[{"event":"qa","target":"qa","description":"Test."}]}\n'
    )
    Assert.that(StatusReport.of(status, AsJson(True))).matches(report)


def test_reads_the_state_from_the_status_store() -> None:
    merging = StateName("merging")
    store = FakeStatusStore(merging)
    Assert.that(StatusReport.of_store(WorkflowChart, store, AsJson(False))).matches(
        Ok(StatusReport.of(FlowStatus.of(WorkflowChart, merging), AsJson(False)))
    )


def test_an_unreachable_store_reports_no_state() -> None:
    reported = StatusReport.of_store(WorkflowChart, UnreachableStatusStore(), AsJson(False))
    Assert.that(reported).matches(Err(WorkspaceManagerError("The workspace board is unreachable.")))


def test_lists_every_state_with_its_description_in_chart_order() -> None:
    states = DescribedStates(
        (
            DescribedState(state=StateName("grill"), description=StateDescription("Unclear.")),
            DescribedState(state=StateName("todo"), description=StateDescription("Clear.")),
        )
    )
    report = StatesReport("grill: Unclear.\ntodo: Clear.\n")
    Assert.that(StatesReport.of(states, AsJson(False))).matches(report)


def test_json_lists_the_same_states_for_scripting() -> None:
    states = DescribedStates(
        (DescribedState(state=StateName("grill"), description=StateDescription("Unclear.")),)
    )
    report = StatesReport('[{"state":"grill","description":"Unclear."}]\n')
    Assert.that(StatesReport.of(states, AsJson(True))).matches(report)
