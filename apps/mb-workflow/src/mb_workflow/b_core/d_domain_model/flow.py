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


# An agent works the ticket in this state, reading the state descriptions to decide what to do.
class AgentWork(Model):
    @staticmethod
    def fake() -> AgentWork:
        return AgentWork()


class AwaitingHuman(Model):
    @staticmethod
    def fake() -> AwaitingHuman:
        return AwaitingHuman()


class Finished(Model):
    @staticmethod
    def fake() -> Finished:
        return Finished()


type NextAction = AgentWork | AwaitingHuman | Finished


# Entry states shape the ticket before work on it starts.
class Phase(StrEnum):
    entry = "entry"
    delivery = "delivery"


# What a ticket in a state looks like, so an agent can tell which state the ticket belongs in.
class StateDescription(Value[str]):
    @staticmethod
    def fake() -> StateDescription:
        return StateDescription("The spec is unclear, so the design is settled with the human.")


# Whether the chart ends in a state. A state ends it when nothing follows, even if someone
# still has to act in it.
class Ending(Value[bool]):
    @staticmethod
    def fake() -> Ending:
        return Ending(False)

    @staticmethod
    def of_action(action: NextAction) -> Ending:
        return Ending(isinstance(action, Finished))


# Each state names its next action and describes itself, so no state can be added without deciding
# what happens in it.
# An entry state can name the delivery state its work opens in, so the ticket shows as delivering
# while the agent works it.
class WorkState(State):
    def __init__(
        self,
        name: StateName,
        action: NextAction,
        phase: Phase,
        description: StateDescription,
        *,
        ending: Ending | None = None,
        opens_in: StateName | None = None,
    ) -> None:
        ends = Ending.of_action(action) if ending is None else ending
        super().__init__(name.root, final=ends.root)
        self.action: NextAction = action
        self.phase: Phase = phase
        self.description: StateDescription = description
        self.opens_in: StateName | None = opens_in


# The first state declared is where the work starts.
class WorkflowChart(StateChart[ChartModel]):
    allow_event_without_transition = False
    catch_errors_as_events = False

    # A ticket enters the flow here when nobody has given it a state, and the agent moves it on.
    triage = WorkState(
        StateName("triage"),
        AgentWork(),
        Phase.entry,
        StateDescription(
            "The ticket has entered the flow, but no one has decided where it belongs. Read it and"
            " move it to the state that fits."
        ),
    )
    grill = WorkState(
        StateName("grill"),
        AgentWork(),
        Phase.entry,
        StateDescription(
            "The problem or the solution is not yet clear enough to implement. Settle the design"
            " with the human by asking questions until both agree."
        ),
    )
    to_ticket = WorkState(
        StateName("to-ticket"),
        AgentWork(),
        Phase.entry,
        StateDescription(
            "The design is settled, but the work is too large for one pull request or is not yet"
            " written down as tickets. Split it into tickets that each fit one pull request."
        ),
    )
    todo = WorkState(
        StateName("todo"),
        AgentWork(),
        Phase.entry,
        StateDescription(
            "The ticket is clear and small enough for one pull request, and no work on it has"
            " started."
        ),
        opens_in=StateName("implementing"),
    )
    implementing = WorkState(
        StateName("implementing"),
        AgentWork(),
        Phase.delivery,
        StateDescription(
            "The ticket is clear and small enough for one pull request. Write the change and its"
            " tests in a draft pull request."
        ),
    )
    # The agent reviews its own work, so it reaches QA already reviewed.
    agent_reviewing = WorkState(
        StateName("agent-reviewing"),
        AgentWork(),
        Phase.delivery,
        StateDescription(
            "The change is written. Review it against the repo's standards and the ticket before"
            " a human sees it."
        ),
    )
    qa = WorkState(
        StateName("qa"),
        AwaitingHuman(),
        Phase.delivery,
        StateDescription("The change is reviewed by the agent and waits for the human to test it."),
    )
    review = WorkState(
        StateName("review"),
        AwaitingHuman(),
        Phase.delivery,
        StateDescription("The pull request is ready and waits for a human reviewer."),
    )
    merging = WorkState(
        StateName("merging"),
        AgentWork(),
        Phase.delivery,
        StateDescription(
            "The change is approved. Push it, resolve conflicts with trunk, and see the pull"
            " request merged."
        ),
    )
    merged = WorkState(
        StateName("merged"),
        Finished(),
        Phase.delivery,
        StateDescription("The pull request is merged, so no work is left."),
    )

    # The agent's own review can find a problem that sends the work back, as implementing can.
    to_grill = Event(
        triage.to(grill) | grill.to.itself() | implementing.to(grill) | agent_reviewing.to(grill),
        id="grill",
        name="grill",
    )
    to_to_ticket = Event(
        triage.to(to_ticket)
        | grill.to(to_ticket)
        | implementing.to(to_ticket)
        | agent_reviewing.to(to_ticket),
        id="to-ticket",
        name="to-ticket",
    )
    to_todo = Event(triage.to(todo) | to_ticket.to(todo), id="todo", name="todo")
    implement = Event(
        triage.to(implementing)
        | grill.to(implementing)
        | to_ticket.to(implementing)
        | todo.to(implementing)
        | implementing.to.itself()
        | agent_reviewing.to(implementing)
        | qa.to(implementing),
        id="implement",
        name="implement",
    )
    agent_review = Event(implementing.to(agent_reviewing), id="agent-review", name="agent-review")
    to_qa = Event(
        implementing.to(qa) | agent_reviewing.to(qa) | review.to(qa) | merging.to(qa),
        id="qa",
        name="qa",
    )
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
        StateName("agent-reviewing"),
        AgentWork(),
        Phase.delivery,
        StateDescription("A teammate's pull request waits for the agent's first-pass review."),
    )
    # The review is mine to finish; finishing it removes the worktree, so the chart ends here.
    reviewing = WorkState(
        StateName("reviewing"),
        AwaitingHuman(),
        Phase.delivery,
        StateDescription("The agent's review is done, and the human finishes the review."),
        ending=Ending(True),
    )

    reviewed = Event(agent_reviewing.to(reviewing), id="reviewed", name="reviewed")


type Chart = type[WorkflowChart] | type[ReviewChart]


class Charts:
    # A worktree reviewing a teammate's pull request follows the review chart; any other follows
    # the workflow chart.
    @staticmethod
    def of_worktree(worktree: Worktree) -> Chart:
        return WorkflowChart if worktree.reviewed_pull_request() is None else ReviewChart


# An entry state that names a delivery state hands its work to that state once a workspace opens.
class WorkspaceOpening:
    @staticmethod
    def state_opened_in(chart: type[WorkflowChart], state: StateName) -> StateName:
        entry = next(
            (
                held
                for held in chart.states
                if isinstance(held, WorkState) and held.name == state.root
            ),
            None,
        )
        if entry is None or entry.opens_in is None:
            return state
        return entry.opens_in


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

    # In event order, as each event leads out of a state along one edge at most.
    def leaving(self, state: StateName) -> tuple[Edge, ...]:
        leaving = {edge.event.root: edge for edge in self.root if edge.source == state}
        return tuple(leaving[event] for event in sorted(leaving))

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


# A legal event with the state it leads to, described so an agent can tell whether it fits.
class EventOption(Model):
    event: EventName
    target: StateName
    description: StateDescription | None

    @staticmethod
    def fake() -> EventOption:
        return EventOption(
            event=EventName.fake(),
            target=StateName("to-ticket"),
            description=StateDescription.fake(),
        )

    @staticmethod
    def of_edge(chart: Chart, edge: Edge) -> EventOption:
        return EventOption(
            event=edge.event,
            target=edge.target,
            description=StateDescriptions.of_state(chart, edge.target),
        )


# A state outside the chart has no description and no legal events.
class FlowStatus(Model):
    state: StateName
    description: StateDescription | None
    events: tuple[EventOption, ...]

    @staticmethod
    def fake() -> FlowStatus:
        return FlowStatus(
            state=StateName.fake(),
            description=StateDescription.fake(),
            events=(EventOption.fake(),),
        )

    @staticmethod
    def of(chart: Chart, state: StateName) -> FlowStatus:
        return FlowStatus(
            state=state,
            description=StateDescriptions.of_state(chart, state),
            events=tuple(
                EventOption.of_edge(chart, edge) for edge in Edges.of_chart(chart).leaving(state)
            ),
        )


class DescribedState(Model):
    state: StateName
    description: StateDescription

    @staticmethod
    def fake() -> DescribedState:
        return DescribedState(state=StateName.fake(), description=StateDescription.fake())


# Every state of a chart in chart order, so an agent can pick the one a ticket belongs in.
class DescribedStates(Value[tuple[DescribedState, ...]]):
    @staticmethod
    def fake() -> DescribedStates:
        return DescribedStates((DescribedState.fake(),))

    @staticmethod
    def of_chart(chart: Chart) -> DescribedStates:
        return DescribedStates(
            tuple(
                DescribedState(state=StateName(state.name), description=state.description)
                for state in chart.states
                if isinstance(state, WorkState)
            )
        )


class StateDescriptions:
    @staticmethod
    def of_state(chart: Chart, state: StateName) -> StateDescription | None:
        return next(
            (
                held.description
                for held in chart.states
                if isinstance(held, WorkState) and held.name == state.root
            ),
            None,
        )
