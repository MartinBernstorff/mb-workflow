import pytest
from assertions import Assert
from safe_result import Ok
from statemachine.exceptions import TransitionNotAllowed

from mb_workflow.b_core.d_domain_model.flow import (
    AcceptedStates,
    Edge,
    Edges,
    EventName,
    EventNames,
    FlowError,
    FlowStatus,
    StateName,
    StateNames,
    UnknownStateError,
    WorkflowChart,
    WorkState,
)

GRILL = StateName("grill")
TO_TICKET = StateName("to-ticket")
TODO = StateName("todo")
IMPLEMENTING = StateName("implementing")
QA = StateName("qa")
REVIEW = StateName("review")
MERGING = StateName("merging")
MERGED = StateName("merged")


def edge(source: StateName, name: EventName, target: StateName) -> Edge:
    return Edge(source=source, event=name, target=target)


def test_the_chart_holds_every_state_the_work_passes_through() -> None:
    Assert.that(StateNames.of_chart(WorkflowChart)).matches(
        StateNames(frozenset({GRILL, TO_TICKET, TODO, IMPLEMENTING, QA, REVIEW, MERGING, MERGED}))
    )


def test_every_state_names_what_happens_in_it() -> None:
    Assert.that(list(WorkflowChart.states)).all(
        lambda state: isinstance(state, WorkState), lambda state: f"{state} is no WorkState"
    )


def test_work_enters_the_chart_at_grilling() -> None:
    Assert.that(StateNames.initial_state(WorkflowChart)).matches(GRILL)


def test_the_chart_holds_every_transition_the_work_can_take() -> None:
    Assert.that(Edges.of_chart(WorkflowChart).root).matches(
        frozenset(
            {
                edge(GRILL, EventName("grill"), GRILL),
                edge(GRILL, EventName("to-ticket"), TO_TICKET),
                edge(TO_TICKET, EventName("todo"), TODO),
                edge(TODO, EventName("implement"), IMPLEMENTING),
                edge(IMPLEMENTING, EventName("qa"), QA),
                edge(IMPLEMENTING, EventName("grill"), GRILL),
                edge(IMPLEMENTING, EventName("to-ticket"), TO_TICKET),
                edge(QA, EventName("implement"), IMPLEMENTING),
                edge(QA, EventName("ready"), REVIEW),
                edge(QA, EventName("merge"), MERGING),
                edge(QA, EventName("resolve-review"), IMPLEMENTING),
                edge(REVIEW, EventName("resolve-review"), IMPLEMENTING),
                edge(REVIEW, EventName("qa"), QA),
                edge(REVIEW, EventName("merge"), MERGING),
                edge(REVIEW, EventName("merged"), MERGED),
                edge(MERGING, EventName("merged"), MERGED),
                edge(MERGING, EventName("qa"), QA),
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
    Assert.that(EventNames.of_state(WorkflowChart, REVIEW)).matches(
        EventNames(
            (
                EventName("merge"),
                EventName("merged"),
                EventName("qa"),
                EventName("resolve-review"),
            )
        )
    )


def test_no_event_is_legal_from_the_final_state() -> None:
    Assert.that(EventNames.of_state(WorkflowChart, MERGED)).matches(EventNames(()))


def test_a_status_pairs_a_state_with_the_events_legal_from_it() -> None:
    Assert.that(FlowStatus.of(WorkflowChart, GRILL)).matches(
        FlowStatus(state=GRILL, events=EventNames((EventName("grill"), EventName("to-ticket"))))
    )


def test_the_chart_names_every_event_it_holds() -> None:
    Assert.that(EventNames.of_chart(WorkflowChart)).matches(
        EventNames(
            (
                EventName("grill"),
                EventName("implement"),
                EventName("merge"),
                EventName("merged"),
                EventName("qa"),
                EventName("ready"),
                EventName("resolve-review"),
                EventName("to-ticket"),
                EventName("todo"),
            )
        )
    )


def test_a_legal_event_leads_to_the_state_the_chart_names() -> None:
    Assert.that(Edges.of_chart(WorkflowChart).target_from(QA, EventName("ready"))).matches(
        Ok(REVIEW)
    )


def test_resolving_a_review_from_qa_returns_the_work_to_implementing() -> None:
    Assert.that(Edges.of_chart(WorkflowChart).target_from(QA, EventName("resolve-review"))).matches(
        Ok(IMPLEMENTING)
    )


def test_an_illegal_event_names_the_current_state_and_the_events_legal_from_it() -> None:
    refused = Edges.of_chart(WorkflowChart).target_from(GRILL, EventName("merge"))
    error = Assert.that(refused.error).is_instance(FlowError)
    Assert.that(str(error)).matches_pattern(
        r"merge is not legal from grill\. Legal: grill, to-ticket\."
    )


def test_an_event_outside_the_chart_is_illegal_from_every_state() -> None:
    refused = Edges.of_chart(WorkflowChart).target_from(QA, EventName("abandon"))
    error = Assert.that(refused.error).is_instance(FlowError)
    Assert.that(str(error)).matches_pattern(r"abandon is not legal from qa\.")


def test_the_final_state_has_no_legal_event_to_offer() -> None:
    refused = Edges.of_chart(WorkflowChart).target_from(MERGED, EventName("merge"))
    error = Assert.that(refused.error).is_instance(FlowError)
    Assert.that(str(error)).matches_pattern(r"Legal: none\.")


def test_forcing_an_event_leads_to_its_state_from_wherever_the_work_sits() -> None:
    Assert.that(Edges.of_chart(WorkflowChart).target_of(EventName("merge"))).matches(Ok(MERGING))


def test_every_event_leads_to_one_state_so_any_of_them_can_be_forced() -> None:
    edges = Edges.of_chart(WorkflowChart)
    states = StateNames.of_chart(WorkflowChart).root
    Assert.that({edges.target_of(name) for name in edges.events().root}).all_in(
        {Ok(state) for state in states}
    )


def test_forcing_an_event_outside_the_chart_lists_the_events_it_holds() -> None:
    refused = Edges.of_chart(WorkflowChart).target_of(EventName("abandon"))
    error = Assert.that(refused.error).is_instance(FlowError)
    Assert.that(str(error)).matches_pattern(
        r"abandon is no event of the chart\. Its events: grill,"
    )


def test_the_events_legal_from_a_state_come_from_the_edges_at_hand() -> None:
    edges = Edges(frozenset({edge(GRILL, EventName("abandon"), MERGED)}))
    refused = edges.target_from(GRILL, EventName("to-ticket"))
    error = Assert.that(refused.error).is_instance(FlowError)
    Assert.that(str(error)).matches_pattern(r"Legal: abandon\.")


@pytest.mark.parametrize("typed", ["todo", "TODO", "Todo"])
def test_a_state_named_in_any_casing_is_spelled_as_the_chart(typed: str) -> None:
    Assert.that(
        AcceptedStates.of_chart(WorkflowChart).named_ignoring_case(StateName(typed))
    ).matches(Ok(TODO))


def test_an_unknown_state_lists_only_the_accepted_states_in_chart_order() -> None:
    unknown = StateName("foo")
    refusal = f"No flow state is named {unknown.root}. Use one of to-ticket, grill."
    looked_up = AcceptedStates((TO_TICKET, GRILL)).named_ignoring_case(unknown)
    error = Assert.that(looked_up.error).is_instance(UnknownStateError)
    Assert.that(str(error)).matches(refusal)
