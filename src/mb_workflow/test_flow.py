import pytest
from statemachine.exceptions import TransitionNotAllowed

from mb_workflow.flow import (
    Edge,
    Edges,
    EventName,
    EventNames,
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
    assert StateNames.of_chart() == StateNames(
        frozenset({GRILLING, SPECCING, SPECCED, IMPLEMENTING, QA, REVIEW, MERGING, MERGED})
    )


def test_work_enters_the_chart_at_grilling() -> None:
    assert StateNames.start() == GRILLING


def test_the_chart_holds_every_transition_the_work_can_take() -> None:
    assert Edges.of_chart() == Edges(
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


def test_the_events_legal_from_a_state_come_off_the_chart() -> None:
    assert EventNames.of_state(REVIEW) == EventNames(
        (
            EventName("merge"),
            EventName("merged"),
            EventName("qa"),
            EventName("resolve-review"),
        )
    )


def test_no_event_is_legal_from_the_state_the_work_ends_in() -> None:
    assert EventNames.of_state(MERGED) == EventNames(())


def test_a_status_pairs_a_state_with_the_events_legal_from_it() -> None:
    assert FlowStatus.of(GRILLING) == FlowStatus.fake()
