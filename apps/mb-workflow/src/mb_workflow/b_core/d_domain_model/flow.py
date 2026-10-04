from enum import StrEnum
from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result
from statemachine import Event, State, StateChart
from statemachine.model import Model as ChartModel

from mb_workflow.d_lib.models import Model, Value

if TYPE_CHECKING:
    from statemachine.transition import Transition


class FlowError(Exception):
    pass


class UnknownStateError(FlowError, ValueError):
    pass


class StateName(Value[str]):
    @staticmethod
    def fake() -> StateName:
        return StateName("Grilling")


class Skill(Value[str]):
    @staticmethod
    def fake() -> Skill:
        return Skill("/implement")


class AwaitingHuman(Model):
    @staticmethod
    def fake() -> AwaitingHuman:
        return AwaitingHuman()


class Finished(Model):
    @staticmethod
    def fake() -> Finished:
        return Finished()


type NextAction = Skill | AwaitingHuman | Finished


# Entry states shape the ticket before work on it starts.
class Phase(StrEnum):
    entry = "entry"
    delivery = "delivery"


# Each state names its next action, so no state can be added without deciding what happens in it.
class WorkState(State):
    def __init__(self, name: StateName, action: NextAction, phase: Phase) -> None:
        super().__init__(name.root, final=isinstance(action, Finished))
        self.action: NextAction = action
        self.phase: Phase = phase


# The first state declared is where the work starts.
class WorkflowChart(StateChart[ChartModel]):
    allow_event_without_transition = False
    catch_errors_as_events = False

    grilling = WorkState(StateName("Grilling"), Skill("/grill"), Phase.entry)
    speccing = WorkState(StateName("Speccing"), Skill("/to-ticket"), Phase.entry)
    specced = WorkState(StateName("Specced"), Skill("/implement"), Phase.entry)
    implementing = WorkState(StateName("Implementing"), Skill("/implement"), Phase.delivery)
    qa = WorkState(StateName("QA"), AwaitingHuman(), Phase.delivery)
    review = WorkState(StateName("Review"), AwaitingHuman(), Phase.delivery)
    merging = WorkState(StateName("Merging"), Skill("/merge"), Phase.delivery)
    merged = WorkState(StateName("Merged"), Finished(), Phase.delivery)

    grill = Event(grilling.to.itself() | implementing.to(grilling), id="grill", name="grill")
    to_ticket = Event(
        grilling.to(speccing) | implementing.to(speccing), id="to-ticket", name="to-ticket"
    )
    to_specced = Event(speccing.to(specced), id="specced", name="specced")
    implement = Event(
        specced.to(implementing) | qa.to(implementing), id="implement", name="implement"
    )
    to_qa = Event(implementing.to(qa) | review.to(qa) | merging.to(qa), id="qa", name="qa")
    ready = Event(qa.to(review), id="ready", name="ready")
    merge = Event(qa.to(merging) | review.to(merging), id="merge", name="merge")
    to_merged = Event(review.to(merged) | merging.to(merged), id="merged", name="merged")
    resolve_review = Event(
        review.to(implementing) | qa.to(implementing), id="resolve-review", name="resolve-review"
    )


class EventName(Value[str]):
    @staticmethod
    def fake() -> EventName:
        return EventName("to-ticket")


class Edge(Model):
    source: StateName
    event: EventName
    target: StateName

    @staticmethod
    def fake() -> Edge:
        return Edge(source=StateName.fake(), event=EventName.fake(), target=StateName("Speccing"))

    @staticmethod
    def of_transition(transition: Transition, name: EventName) -> Edge:
        if transition.target is None:
            # lint-fixme: NoRaise
            raise ValueError(f"{name.root} leads nowhere out of {transition.source.name}.")
        return Edge(
            source=StateName(transition.source.name),
            event=name,
            target=StateName(transition.target.name),
        )


class Edges(Value[frozenset[Edge]]):
    @staticmethod
    def fake() -> Edges:
        return Edges(frozenset({Edge.fake()}))

    @staticmethod
    def of_chart(chart: type[WorkflowChart]) -> Edges:
        return Edges(
            frozenset(
                Edge.of_transition(transition, EventName(str(name)))
                for state in chart.states
                for transition in state.transitions
                for name in transition.events
            )
        )

    def events(self) -> EventNames:
        return EventNames.of(frozenset(edge.event for edge in self.root))

    def events_from(self, state: StateName) -> EventNames:
        return EventNames.of(frozenset(edge.event for edge in self.root if edge.source == state))

    def target_from(self, state: StateName, event: EventName) -> Result[StateName, FlowError]:
        for edge in self.root:
            if edge.source == state and edge.event == event:
                return Ok(edge.target)
        legal = ", ".join(name.root for name in self.events_from(state).root)
        return Err(
            FlowError(f"{event.root} is not legal from {state.root}. Legal: {legal or 'none'}.")
        )

    def target_of(self, event: EventName) -> Result[StateName, FlowError]:
        targets = {edge.target for edge in self.root if edge.event == event}
        if len(targets) == 1:
            return Ok(targets.pop())
        known = ", ".join(name.root for name in self.events().root)
        return Err(FlowError(f"{event.root} is no event of the chart. Its events: {known}."))


class StateNames(Value[frozenset[StateName]]):
    @staticmethod
    def fake() -> StateNames:
        return StateNames(frozenset({StateName.fake()}))

    @staticmethod
    def of_chart(chart: type[WorkflowChart]) -> StateNames:
        return StateNames(frozenset(StateName(state.name) for state in chart.states))

    @staticmethod
    def initial_state(chart: type[WorkflowChart]) -> StateName:
        initial = chart.initial_state
        if initial is None:
            # lint-fixme: NoRaise
            raise ValueError("The chart has no state to start in.")
        return StateName(initial.name)


# The states a caller accepts, in chart order, so a typed name is spelled as the chart spells it.
class AcceptedStates(Value[tuple[StateName, ...]]):
    @staticmethod
    def fake() -> AcceptedStates:
        return AcceptedStates((StateName.fake(),))

    @staticmethod
    def of_chart(chart: type[WorkflowChart]) -> AcceptedStates:
        return AcceptedStates(tuple(StateName(state.name) for state in chart.states))

    def named_ignoring_case(self, name: StateName) -> Result[StateName, UnknownStateError]:
        wanted = name.root.casefold()
        for state in self.root:
            if state.root.casefold() == wanted:
                return Ok(state)
        listed = ", ".join(state.root for state in self.root)
        return Err(UnknownStateError(f"No flow state is named {name.root}. Use one of {listed}."))


class EventNames(Value[tuple[EventName, ...]]):
    @staticmethod
    def fake() -> EventNames:
        return EventNames((EventName.fake(),))

    @staticmethod
    def of(names: frozenset[EventName]) -> EventNames:
        return EventNames(tuple(EventName(text) for text in sorted(name.root for name in names)))

    @staticmethod
    def of_chart(chart: type[WorkflowChart]) -> EventNames:
        return Edges.of_chart(chart).events()

    @staticmethod
    def of_state(chart: type[WorkflowChart], state: StateName) -> EventNames:
        return Edges.of_chart(chart).events_from(state)


class FlowStatus(Model):
    state: StateName
    events: EventNames

    @staticmethod
    def fake() -> FlowStatus:
        return FlowStatus(state=StateName.fake(), events=EventNames.fake())

    @staticmethod
    def of(chart: type[WorkflowChart], state: StateName) -> FlowStatus:
        return FlowStatus(state=state, events=EventNames.of_state(chart, state))
