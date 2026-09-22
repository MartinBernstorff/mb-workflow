import pytest
from statemachine.exceptions import TransitionNotAllowed

from mb_workflow.b_core.d_domain_model.flow import (
    Edge,
    Edges,
    EventName,
    EventNames,
    FlowError,
    FlowStatus,
    StateName,
    StateNames,
    WorkflowChart,
)

GRILLING = StateName("Grilling")
SPECCING = StateName("Speccing")
SPECCED = StateName("Specced")
IMPLEMENTING = StateName("Implementing")
QA = StateName("QA")
REVIEW = StateName("Review")
MERGING = StateName("Merging")
MERGED = StateName("Merged")


def edge(source: StateName, name: EventName, target: StateName) -> Edge:
    return Edge(source=source, event=name, target=target)


def test_the_chart_holds_every_state_the_work_passes_through() -> None:
    assert StateNames.of_chart(WorkflowChart) == StateNames(
        frozenset({GRILLING, SPECCING, SPECCED, IMPLEMENTING, QA, REVIEW, MERGING, MERGED})
    )


def test_work_enters_the_chart_at_grilling() -> None:
    assert StateNames.start(WorkflowChart) == GRILLING


def test_the_chart_holds_every_transition_the_work_can_take() -> None:
    assert Edges.of_chart(WorkflowChart) == Edges(
        frozenset(
            {
                edge(GRILLING, EventName("to-ticket"), SPECCING),
                edge(SPECCING, EventName("specced"), SPECCED),
                edge(SPECCED, EventName("implement"), IMPLEMENTING),
                edge(IMPLEMENTING, EventName("qa"), QA),
                edge(IMPLEMENTING, EventName("grill"), GRILLING),
                edge(IMPLEMENTING, EventName("to-ticket"), SPECCING),
                edge(QA, EventName("implement"), IMPLEMENTING),
                edge(QA, EventName("ready"), REVIEW),
                edge(QA, EventName("merge"), MERGING),
                edge(REVIEW, EventName("resolve-review"), IMPLEMENTING),
                edge(REVIEW, EventName("qa"), QA),
                edge(REVIEW, EventName("merge"), MERGING),
                edge(REVIEW, EventName("merged"), MERGED),
                edge(MERGING, EventName("merged"), MERGED),
            }
        )
    )


def test_an_event_with_no_transition_from_the_current_state_raises() -> None:
    with pytest.raises(TransitionNotAllowed):
        WorkflowChart().send(EventName("merge").root)


def test_an_event_the_chart_has_never_heard_of_raises() -> None:
    with pytest.raises(TransitionNotAllowed):
        WorkflowChart().send(EventName("abandon").root)


def test_an_exception_raised_during_a_transition_propagates() -> None:
    class Detonator:
        def on_transition(self) -> None:
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        WorkflowChart(listeners=[Detonator()]).send(EventName("to-ticket").root)


def test_the_events_legal_from_a_state_come_from_the_chart() -> None:
    assert EventNames.of_state(WorkflowChart, REVIEW) == EventNames(
        (
            EventName("merge"),
            EventName("merged"),
            EventName("qa"),
            EventName("resolve-review"),
        )
    )


def test_no_event_is_legal_from_the_final_state() -> None:
    assert EventNames.of_state(WorkflowChart, MERGED) == EventNames(())


def test_a_status_pairs_a_state_with_the_events_legal_from_it() -> None:
    assert FlowStatus.of(WorkflowChart, GRILLING) == FlowStatus(
        state=GRILLING, events=EventNames((EventName("to-ticket"),))
    )


def test_the_chart_names_every_event_it_holds() -> None:
    assert EventNames.of_chart(WorkflowChart) == EventNames(
        (
            EventName("grill"),
            EventName("implement"),
            EventName("merge"),
            EventName("merged"),
            EventName("qa"),
            EventName("ready"),
            EventName("resolve-review"),
            EventName("specced"),
            EventName("to-ticket"),
        )
    )


def test_a_legal_event_leads_to_the_state_the_chart_names() -> None:
    assert Edges.of_chart(WorkflowChart).target_from(QA, EventName("ready")) == REVIEW


def test_an_illegal_event_names_the_current_state_and_the_events_legal_from_it() -> None:
    with pytest.raises(FlowError, match=r"merge is not legal from Grilling\. Legal: to-ticket\."):
        _ = Edges.of_chart(WorkflowChart).target_from(GRILLING, EventName("merge"))


def test_an_event_outside_the_chart_is_illegal_from_every_state() -> None:
    with pytest.raises(FlowError, match=r"abandon is not legal from QA\."):
        _ = Edges.of_chart(WorkflowChart).target_from(QA, EventName("abandon"))


def test_the_final_state_has_no_legal_event_to_offer() -> None:
    with pytest.raises(FlowError, match=r"Legal: none\."):
        _ = Edges.of_chart(WorkflowChart).target_from(MERGED, EventName("merge"))


def test_forcing_an_event_leads_to_its_state_from_wherever_the_work_sits() -> None:
    assert Edges.of_chart(WorkflowChart).target_of(EventName("merge")) == MERGING


def test_every_event_leads_to_one_state_so_any_of_them_can_be_forced() -> None:
    edges = Edges.of_chart(WorkflowChart)
    assert {edges.target_of(name) for name in edges.events().root} <= StateNames.of_chart(
        WorkflowChart
    ).root


def test_forcing_an_event_outside_the_chart_lists_the_events_it_holds() -> None:
    with pytest.raises(FlowError, match=r"abandon is no event of the chart\. Its events: grill,"):
        _ = Edges.of_chart(WorkflowChart).target_of(EventName("abandon"))


def test_the_events_legal_from_a_state_come_from_the_edges_at_hand() -> None:
    edges = Edges(frozenset({edge(GRILLING, EventName("abandon"), MERGED)}))
    with pytest.raises(FlowError, match=r"Legal: abandon\."):
        _ = edges.target_from(GRILLING, EventName("to-ticket"))
