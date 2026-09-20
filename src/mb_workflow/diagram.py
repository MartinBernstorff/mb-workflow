import logging
import sys
from pathlib import Path

from statemachine.contrib.diagram import DotGraphMachine, MermaidGraphMachine

from mb_workflow.flow import WorkflowChart
from mb_workflow.models import Value
from mb_workflow.shell import ExitCode

logger = logging.getLogger(__name__)


class MermaidDiagram(Value[str]):
    @staticmethod
    def fake() -> MermaidDiagram:
        return MermaidDiagram("stateDiagram-v2\n    direction LR\n    [*] --> grilling\n")


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
            raise ValueError(
                f"{destination.root} has no extension, and the extension picks the image format."
            )
        return ImageFormat(suffix)


def render_mermaid() -> MermaidDiagram:
    return MermaidDiagram(MermaidGraphMachine(WorkflowChart).get_mermaid())


def write_image(destination: DiagramPath) -> None:
    image_format = ImageFormat.of(destination)
    graph = DotGraphMachine(WorkflowChart).get_graph()
    _ = graph.write(str(destination.root), format=image_format.root)


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
