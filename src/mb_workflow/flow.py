import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from statemachine import Event, State, StateMachine
from statemachine.contrib.diagram import DotGraphMachine, MermaidGraphMachine

from mb_workflow.models import Model, Value
from mb_workflow.shell import ExitCode

if TYPE_CHECKING:
    from statemachine.transition import Transition

logger = logging.getLogger(__name__)


class WorkflowChart(StateMachine):
    allow_event_without_transition = False
    catch_errors_as_events = False

    grilling = State("Grilling", initial=True)
    speccing = State("Speccing")
    specced = State("Specced")
    implementing = State("Implementing")
    qa = State("QA")
    review = State("Review")
    merging = State("Merging")
    merged = State("Merged", final=True)

    grill = Event(implementing.to(grilling), id="grill", name="grill")
    to_ticket = Event(
        grilling.to(speccing) | implementing.to(speccing), id="to-ticket", name="to-ticket"
    )
    spec_written = Event(speccing.to(specced), id="specced", name="specced")
    implement = Event(
        specced.to(implementing) | qa.to(implementing), id="implement", name="implement"
    )
    check = Event(implementing.to(qa) | review.to(qa), id="qa", name="qa")
    ready = Event(qa.to(review), id="ready", name="ready")
    merge = Event(qa.to(merging) | review.to(merging), id="merge", name="merge")
    landed = Event(review.to(merged) | merging.to(merged), id="merged", name="merged")
    resolve_review = Event(review.to(implementing), id="resolve-review", name="resolve-review")


class StateName(Value[str]):
    @staticmethod
    def fake() -> StateName:
        return StateName("Grilling")

    @staticmethod
    def of_target(transition: Transition) -> StateName:
        if transition.target is None:
            raise ValueError(f"{transition} leads nowhere.")
        return StateName(transition.target.name)

    @staticmethod
    def start() -> StateName:
        initial = WorkflowChart.initial_state
        if initial is None:
            raise ValueError("The chart has no state to start in.")
        return StateName(initial.name)


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


class Edges(Value[frozenset[Edge]]):
    @staticmethod
    def fake() -> Edges:
        return Edges(frozenset({Edge.fake()}))

    @staticmethod
    def of_chart() -> Edges:
        return Edges(
            frozenset(
                Edge(
                    source=StateName(transition.source.name),
                    event=EventName(str(event)),
                    target=StateName.of_target(transition),
                )
                for state in WorkflowChart.states
                for transition in state.transitions
                for event in transition.events
            )
        )


class StateNames(Value[frozenset[StateName]]):
    @staticmethod
    def fake() -> StateNames:
        return StateNames(frozenset({StateName.fake()}))

    @staticmethod
    def of_chart() -> StateNames:
        return StateNames(frozenset(StateName(state.name) for state in WorkflowChart.states))


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
    destination.root.parent.mkdir(parents=True, exist_ok=True)
    _ = (
        DotGraphMachine(WorkflowChart)
        .get_graph()
        .write(str(destination.root), format=image_format.root)
    )


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
