import logging
import sys
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from statemachine import Event, State, StateMachine
from statemachine.contrib.diagram import DotGraphMachine, MermaidGraphMachine
from statemachine.states import States

from mb_workflow.models import Model, Value
from mb_workflow.shell import ExitCode

if TYPE_CHECKING:
    from statemachine.transition import Transition
    from statemachine.transition_list import TransitionList

logger = logging.getLogger(__name__)


class Stage(StrEnum):
    grilling = "Grilling"
    speccing = "Speccing"
    specced = "Specced"
    implementing = "Implementing"
    qa = "QA"
    review = "Review"
    merging = "Merging"
    merged = "Merged"


class EventName(Value[str]):
    @staticmethod
    def fake() -> EventName:
        return EventName("to-ticket")


def event(transitions: TransitionList, name: EventName) -> Event:
    return Event(transitions, id=name.root, name=name.root)


class WorkflowChart(StateMachine):
    allow_event_without_transition = False
    catch_errors_as_events = False

    stages = States(
        {
            stage.name: State(
                stage.value,
                value=stage,
                initial=stage is Stage.grilling,
                final=stage is Stage.merged,
            )
            for stage in Stage
        }
    )

    grill = event(stages.implementing.to(stages.grilling), EventName("grill"))
    to_ticket = event(
        stages.grilling.to(stages.speccing) | stages.implementing.to(stages.speccing),
        EventName("to-ticket"),
    )
    specced = event(stages.speccing.to(stages.specced), EventName("specced"))
    implement = event(
        stages.specced.to(stages.implementing) | stages.qa.to(stages.implementing),
        EventName("implement"),
    )
    qa = event(stages.implementing.to(stages.qa) | stages.review.to(stages.qa), EventName("qa"))
    ready = event(stages.qa.to(stages.review), EventName("ready"))
    merge = event(
        stages.qa.to(stages.merging) | stages.review.to(stages.merging), EventName("merge")
    )
    merged = event(
        stages.review.to(stages.merged) | stages.merging.to(stages.merged), EventName("merged")
    )
    resolve_review = event(stages.review.to(stages.implementing), EventName("resolve-review"))


class Edge(Model):
    source: Stage
    event: EventName
    target: Stage

    @staticmethod
    def fake() -> Edge:
        return Edge(source=Stage.grilling, event=EventName.fake(), target=Stage.speccing)

    @staticmethod
    def of_transition(transition: Transition, name: EventName) -> Edge:
        if transition.target is None:
            raise ValueError(f"{name.root} leads nowhere out of {transition.source.value}.")
        return Edge(
            source=Stage(transition.source.value),
            event=name,
            target=Stage(transition.target.value),
        )


class Edges(Value[frozenset[Edge]]):
    @staticmethod
    def fake() -> Edges:
        return Edges(frozenset({Edge.fake()}))

    @staticmethod
    def of_chart() -> Edges:
        return Edges(
            frozenset(
                Edge.of_transition(transition, EventName(str(name)))
                for state in WorkflowChart.states
                for transition in state.transitions
                for name in transition.events
            )
        )


class Stages(Value[frozenset[Stage]]):
    @staticmethod
    def fake() -> Stages:
        return Stages(frozenset({Stage.grilling}))

    @staticmethod
    def of_chart() -> Stages:
        return Stages(frozenset(Stage(state.value) for state in WorkflowChart.states))

    @staticmethod
    def start() -> Stage:
        initial = WorkflowChart.initial_state
        if initial is None:
            raise ValueError("The chart has no stage to start in.")
        return Stage(initial.value)


class MermaidDiagram(Value[str]):
    @staticmethod
    def fake() -> MermaidDiagram:
        return MermaidDiagram("stateDiagram-v2\n    direction LR\n    [*] --> grilling\n")


class DiagramPath(Value[Path]):
    @staticmethod
    def fake() -> DiagramPath:
        return DiagramPath(Path("flow.png"))


class ImageFormat(Value[str]):
    @staticmethod
    def fake() -> ImageFormat:
        return ImageFormat("png")

    @staticmethod
    def of(destination: DiagramPath) -> ImageFormat:
        suffix = destination.root.suffix.removeprefix(".")
        if not suffix:
            raise ValueError(
                f"{destination.root} has no extension, and the extension picks the image format."
            )
        return ImageFormat(suffix)


def render_mermaid() -> MermaidDiagram:
    return MermaidDiagram(MermaidGraphMachine(WorkflowChart).get_mermaid())


def write_image(destination: DiagramPath) -> None:
    image_format = ImageFormat.of(destination)
    graph = DotGraphMachine(WorkflowChart).get_graph()
    # pydot reports a rejected format by asserting on the exit code of `dot`.
    try:
        _ = graph.write(str(destination.root), format=image_format.root)
    except AssertionError as error:
        raise ValueError(f"Graphviz does not know the {image_format.root} format.") from error


def diagram(destination: DiagramPath | None) -> ExitCode:
    if destination is None:
        _ = sys.stdout.write(render_mermaid().root)
        return ExitCode(0)
    try:
        write_image(destination)
    except OSError as error:
        logger.error("Could not write %s: %s", destination.root, error)
        return ExitCode(1)
    except ValueError as error:
        logger.error("%s", error)
        return ExitCode(1)
    logger.info("Wrote %s", destination.root)
    return ExitCode(0)
