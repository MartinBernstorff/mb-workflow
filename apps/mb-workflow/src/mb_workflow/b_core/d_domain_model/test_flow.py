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
    WorkspaceOpening,
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
    for state in WorkflowChart.states:
        _ = Assert.that(state).is_instance(WorkState)


def test_work_enters_the_chart_at_grilling() -> None:
    Assert.that(StateNames.initial_state(WorkflowChart)).matches(GRILL)


def test_the_chart_holds_every_transition_the_work_can_take() -> None:
    every_transition = Edges(
        frozenset(
            {
                edge(GRILL, EventName("grill"), GRILL),
                edge(GRILL, EventName("to-ticket"), TO_TICKET),
                edge(TO_TICKET, EventName("todo"), TODO),
                edge(TODO, EventName("implement"), IMPLEMENTING),
                edge(IMPLEMENTING, EventName("implement"), IMPLEMENTING),
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
    Assert.that(Edges.of_chart(WorkflowChart)).matches(every_transition)


def test_an_event_with_no_transition_from_the_current_state_raises() -> None:
    with pytest.raises(TransitionNotAllowed):
        WorkflowChart().send(EventName("merge").root)


def test_an_event_the_chart_has_never_heard_of_raises() -> None:
    with pytest.raises(TransitionNotAllowed):
        WorkflowChart().send(EventName("abandon").root)


def test_an_exception_raised_during_a_transition_propagates() -> None:
    explosion = "boom"

    class Detonator:
        def on_transition(self) -> None:
            raise RuntimeError(explosion)

    with pytest.raises(RuntimeError, match=explosion):
        WorkflowChart(listeners=[Detonator()]).send(EventName("to-ticket").root)


def test_the_events_legal_from_a_state_come_from_the_chart() -> None:
    legal_from_review = EventNames(
        (
            EventName("merge"),
            EventName("merged"),
            EventName("qa"),
            EventName("resolve-review"),
        )
    )
    Assert.that(EventNames.of_state(WorkflowChart, REVIEW)).matches(legal_from_review)


def test_no_event_is_legal_from_the_final_state() -> None:
    Assert.that(EventNames.of_state(WorkflowChart, MERGED)).matches(EventNames(()))


def test_a_status_pairs_a_state_with_the_events_legal_from_it() -> None:
    grill_status = FlowStatus(
        state=GRILL, events=EventNames((EventName("grill"), EventName("to-ticket")))
    )
    Assert.that(FlowStatus.of(WorkflowChart, GRILL)).matches(grill_status)


def test_the_chart_names_every_event_it_holds() -> None:
    every_event = EventNames(
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
    Assert.that(EventNames.of_chart(WorkflowChart)).matches(every_event)


def test_a_legal_event_leads_to_the_state_the_chart_names() -> None:
    Assert.that(Edges.of_chart(WorkflowChart).target_from(QA, EventName("ready"))).matches(
        Ok(REVIEW)
    )


def test_implementing_again_keeps_the_work_in_implementing() -> None:
    Assert.that(
        Edges.of_chart(WorkflowChart).target_from(IMPLEMENTING, EventName("implement"))
    ).matches(Ok(IMPLEMENTING))


def test_only_todo_opens_in_the_delivery_state_running_the_same_skill() -> None:
    opened = {
        state: WorkspaceOpening.state_opened_in(WorkflowChart, state)
        for state in StateNames.of_chart(WorkflowChart).root
    }
    moved = {state: target for state, target in opened.items() if target != state}
    Assert.that(moved).matches({TODO: IMPLEMENTING})


def test_resolving_a_review_from_qa_returns_the_work_to_implementing() -> None:
    Assert.that(Edges.of_chart(WorkflowChart).target_from(QA, EventName("resolve-review"))).matches(
        Ok(IMPLEMENTING)
    )


def test_an_illegal_event_names_the_current_state_and_the_events_legal_from_it() -> None:
    merge = EventName("merge")
    refusal = rf"{merge.root} is not legal from {GRILL.root}\. Legal: grill, to-ticket\."
    refused = Edges.of_chart(WorkflowChart).target_from(GRILL, merge)
    error = Assert.that(refused.error).is_instance(FlowError)
    Assert.that(str(error)).matches_pattern(refusal)


def test_an_event_outside_the_chart_is_illegal_from_every_state() -> None:
    abandon = EventName("abandon")
    refusal = rf"{abandon.root} is not legal from {QA.root}\."
    refused = Edges.of_chart(WorkflowChart).target_from(QA, abandon)
    error = Assert.that(refused.error).is_instance(FlowError)
    Assert.that(str(error)).matches_pattern(refusal)


def test_the_final_state_has_no_legal_event_to_offer() -> None:
    no_legal_event = r"Legal: none\."
    refused = Edges.of_chart(WorkflowChart).target_from(MERGED, EventName("merge"))
    error = Assert.that(refused.error).is_instance(FlowError)
    Assert.that(str(error)).matches_pattern(no_legal_event)


def test_forcing_an_event_leads_to_its_state_from_wherever_the_work_sits() -> None:
    Assert.that(Edges.of_chart(WorkflowChart).target_of(EventName("merge"))).matches(Ok(MERGING))


def test_every_event_leads_to_one_state_so_any_of_them_can_be_forced() -> None:
    edges = Edges.of_chart(WorkflowChart)
    states = StateNames.of_chart(WorkflowChart).root
    Assert.that({edges.target_of(name) for name in edges.events().root}).all_in(
        {Ok(state) for state in states}
    )


def test_forcing_an_event_outside_the_chart_lists_the_events_it_holds() -> None:
    abandon = EventName("abandon")
    refusal = rf"{abandon.root} is no event of the chart\. Its events: grill,"
    refused = Edges.of_chart(WorkflowChart).target_of(abandon)
    error = Assert.that(refused.error).is_instance(FlowError)
    Assert.that(str(error)).matches_pattern(refusal)


def test_the_events_legal_from_a_state_come_from_the_edges_at_hand() -> None:
    abandon = EventName("abandon")
    legal_events = rf"Legal: {abandon.root}\."
    edges = Edges(frozenset({edge(GRILL, abandon, MERGED)}))
    refused = edges.target_from(GRILL, EventName("to-ticket"))
    error = Assert.that(refused.error).is_instance(FlowError)
    Assert.that(str(error)).matches_pattern(legal_events)


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
