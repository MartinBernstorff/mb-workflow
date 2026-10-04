import logging
import re
import sys
from pathlib import Path

import pydot
from statemachine.contrib.diagram import DotGraphMachine, MermaidGraphMachine

from mb_workflow.a_presentation.console import ExitCode
from mb_workflow.b_core.d_domain_model.flow import WorkflowChart
from mb_workflow.d_lib.models import Model, Value

logger = logging.getLogger(__name__)


class MermaidDiagram(Value[str]):
    @staticmethod
    def fake() -> MermaidDiagram:
        return MermaidDiagram("stateDiagram-v2\n    direction LR\n    [*] --> grilling\n")


class MermaidDocument(Value[str]):
    @staticmethod
    def fake() -> MermaidDocument:
        return MermaidDocument.of(MermaidDiagram.fake())

    @staticmethod
    def of(diagram: MermaidDiagram) -> MermaidDocument:
        return MermaidDocument(f"```mermaid\n{diagram.root.rstrip()}\n```\n")


class DiagramPath(Value[Path]):
    @staticmethod
    def fake() -> DiagramPath:
        return DiagramPath(Path("flow.svg"))


class ImageFormat(Value[str]):
    @staticmethod
    def fake() -> ImageFormat:
        return ImageFormat("svg")

    @staticmethod
    def of(destination: DiagramPath) -> ImageFormat:
        suffix = destination.root.suffix.removeprefix(".")
        if not suffix:
            # lint-fixme: NoRaise
            raise ValueError(
                f"{destination.root} has no extension, and the extension picks the image format."
            )
        return ImageFormat(suffix)


class MermaidFormat(Model):
    @staticmethod
    def fake() -> MermaidFormat:
        return MermaidFormat()


def format_of(destination: DiagramPath) -> MermaidFormat | ImageFormat:
    if destination.root.suffix == ".md":
        return MermaidFormat()
    return ImageFormat.of(destination)


class DotSource(Value[str]):
    @staticmethod
    def fake() -> DotSource:
        return DotSource("digraph WorkflowChart {\n__initial_0 -> grilling;\n}\n")

    def with_stable_ids(self) -> DotSource:
        # The library names the initial node and atomic cluster after id() of their parent graph, which differs every run.
        prefix = r"(__initial_|cluster___atomic_)"
        identities = dict.fromkeys(
            match.group(2) for match in re.finditer(rf"{prefix}(\d+)", self.root)
        )
        source = self.root
        for ordinal, identity in enumerate(identities):
            source = re.sub(rf"{prefix}{identity}(?!\d)", rf"\g<1>{ordinal}", source)
        return DotSource(source)


def render_mermaid() -> MermaidDiagram:
    return MermaidDiagram(MermaidGraphMachine(WorkflowChart).get_mermaid())


def render_dot() -> DotSource:
    return DotSource(DotGraphMachine(WorkflowChart).get_graph().to_string()).with_stable_ids()


def write_image(destination: DiagramPath, image_format: ImageFormat) -> None:
    graphs = pydot.graph_from_dot_data(render_dot().root)
    if not graphs:
        # lint-fixme: NoRaise
        raise ValueError("The chart's DOT source could not be parsed.")
    _ = graphs[0].write(str(destination.root), format=image_format.root)


def write_mermaid(destination: DiagramPath) -> None:
    _ = destination.root.write_text(MermaidDocument.of(render_mermaid()).root)


def write_diagram(destination: DiagramPath) -> None:
    match format_of(destination):
        case MermaidFormat():
            write_mermaid(destination)
        case ImageFormat() as image_format:
            write_image(destination, image_format)


def diagram(destination: DiagramPath | None) -> ExitCode:
    if destination is None:
        _ = sys.stdout.write(render_mermaid().root)
        return ExitCode(0)
    try:
        write_diagram(destination)
    except OSError as error:
        logger.error("Could not write %s: %s", destination.root, error)
        return ExitCode(1)
    except ValueError as error:
        logger.error("%s", error)
        return ExitCode(1)
    logger.info("Wrote %s", destination.root)
    return ExitCode(0)
