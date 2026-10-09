from enum import StrEnum
from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result
from statemachine import Event, State, StateChart
from statemachine.model import Model as ChartModel

from mb_workflow.d_lib.models import Model, Value

if TYPE_CHECKING:
    from statemachine.transition import Transition

    from mb_workflow.b_core.d_domain_model.workspace import Worktree


class FlowError(Exception):
    pass


class UnknownStateError(FlowError, ValueError):
    pass


class StateName(Value[str]):
    @staticmethod
    def fake() -> StateName:
        return StateName("grill")


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


# Whether the chart ends in a state. A state ends it when nothing follows, even if someone
# still has to act in it.
class Ending(Value[bool]):
    @staticmethod
    def fake() -> Ending:
        return Ending(False)

    @staticmethod
    def of_action(action: NextAction) -> Ending:
        return Ending(isinstance(action, Finished))


# Each state names its next action, so no state can be added without deciding what happens in it.
class WorkState(State):
    def __init__(
        self, name: StateName, action: NextAction, phase: Phase, ending: Ending | None = None
    ) -> None:
        ends = Ending.of_action(action) if ending is None else ending
        super().__init__(name.root, final=ends.root)
        self.action: NextAction = action
        self.phase: Phase = phase


# The first state declared is where the work starts.
class WorkflowChart(StateChart[ChartModel]):
    allow_event_without_transition = False
    catch_errors_as_events = False

    grill = WorkState(StateName("grill"), Skill("/grill"), Phase.entry)
    to_ticket = WorkState(StateName("to-ticket"), Skill("/to-ticket"), Phase.entry)
    todo = WorkState(StateName("todo"), Skill("/implement"), Phase.entry)
    implementing = WorkState(StateName("implementing"), Skill("/implement"), Phase.delivery)
    # The agent reviews its own work, so it reaches QA already reviewed.
    agent_reviewing = WorkState(StateName("agent-reviewing"), Skill("/review-mine"), Phase.delivery)
    qa = WorkState(StateName("qa"), AwaitingHuman(), Phase.delivery)
    review = WorkState(StateName("review"), AwaitingHuman(), Phase.delivery)
    merging = WorkState(StateName("merging"), Skill("/merge"), Phase.delivery)
    merged = WorkState(StateName("merged"), Finished(), Phase.delivery)

    # The agent's own review can find a problem that sends the work back, as implementing can.
    to_grill = Event(
        grill.to.itself() | implementing.to(grill) | agent_reviewing.to(grill),
        id="grill",
        name="grill",
    )
    to_to_ticket = Event(
        grill.to(to_ticket) | implementing.to(to_ticket) | agent_reviewing.to(to_ticket),
        id="to-ticket",
        name="to-ticket",
    )
    to_todo = Event(to_ticket.to(todo), id="todo", name="todo")
    implement = Event(
        todo.to(implementing)
        | implementing.to.itself()
        | agent_reviewing.to(implementing)
        | qa.to(implementing),
        id="implement",
        name="implement",
    )
    agent_review = Event(implementing.to(agent_reviewing), id="agent-review", name="agent-review")
    to_qa = Event(agent_reviewing.to(qa) | review.to(qa) | merging.to(qa), id="qa", name="qa")
    ready = Event(qa.to(review), id="ready", name="ready")
    merge = Event(qa.to(merging) | review.to(merging), id="merge", name="merge")
    to_merged = Event(review.to(merged) | merging.to(merged), id="merged", name="merged")
    resolve_review = Event(
        review.to(implementing) | qa.to(implementing), id="resolve-review", name="resolve-review"
    )


# A teammate's pull request I review. It has no ticket of mine, so its state lives only on the
# board and never reaches the ticket tracker; that is why it is a chart of its own, whose states
# need no ticket status.
class ReviewChart(StateChart[ChartModel]):
    allow_event_without_transition = False
    catch_errors_as_events = False

    agent_reviewing = WorkState(
        StateName("agent-reviewing"), Skill("/review-others"), Phase.delivery
    )
    # The review is mine to finish; finishing it removes the worktree, so the chart ends here.
    reviewing = WorkState(StateName("reviewing"), AwaitingHuman(), Phase.delivery, Ending(True))

    reviewed = Event(agent_reviewing.to(reviewing), id="reviewed", name="reviewed")


type Chart = type[WorkflowChart] | type[ReviewChart]


class Charts:
    # A worktree reviewing a teammate's pull request follows the review chart; any other follows
    # the workflow chart.
    @staticmethod
    def of_worktree(worktree: Worktree) -> Chart:
        return WorkflowChart if worktree.reviewed_pull_request() is None else ReviewChart


# An entry state whose skill a delivery state also runs hands its work to that delivery state
# once a workspace opens, so the ticket shows as delivering while the skill runs.
class WorkspaceOpening:
    @staticmethod
    def state_opened_in(chart: type[WorkflowChart], state: StateName) -> StateName:
        work_states = [held for held in chart.states if isinstance(held, WorkState)]
        entry = next(
            (
                held
                for held in work_states
                if held.name == state.root
                and held.phase == Phase.entry
                and isinstance(held.action, Skill)
            ),
            None,
        )
        if entry is None:
            return state
        return next(
            (
                StateName(held.name)
                for held in work_states
                if held.phase == Phase.delivery and held.action == entry.action
            ),
            state,
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
        return Edge(source=StateName.fake(), event=EventName.fake(), target=StateName("to-ticket"))

    @staticmethod
    def of_transition(transition: Transition, name: EventName) -> Edge:
        if transition.target is None:
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
    def of_chart(chart: Chart) -> Edges:
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
            FlowError(
                f"{event.root} is not legal from {state.root}. Legal: {legal or 'none'}. "
                "Use --force to do it anyway."
            )
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
    def of_chart(chart: Chart) -> StateNames:
        return StateNames(frozenset(StateName(state.name) for state in chart.states))

    @staticmethod
    def initial_state(chart: Chart) -> StateName:
        initial = chart.initial_state
        if initial is None:
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
    def of_chart(chart: Chart) -> EventNames:
        return Edges.of_chart(chart).events()

    @staticmethod
    def of_state(chart: Chart, state: StateName) -> EventNames:
        return Edges.of_chart(chart).events_from(state)


class FlowStatus(Model):
    state: StateName
    events: EventNames

    @staticmethod
    def fake() -> FlowStatus:
        return FlowStatus(state=StateName.fake(), events=EventNames.fake())

    @staticmethod
    def of(chart: Chart, state: StateName) -> FlowStatus:
        return FlowStatus(state=state, events=EventNames.of_state(chart, state))
