import logging
import re
import sys
from enum import StrEnum
from pathlib import Path

import pydot
from statemachine.contrib.diagram import DotGraphMachine, MermaidGraphMachine

from mb_workflow.a_presentation.console import ExitCode
from mb_workflow.b_core.d_domain_model.flow import Chart, ReviewChart, WorkflowChart
from mb_workflow.d_lib.models import Model, Value

logger = logging.getLogger(__name__)


class ChartName(StrEnum):
    workflow = "workflow"
    review = "review"

    @staticmethod
    def fake() -> ChartName:
        return ChartName.workflow

    def to_chart(self) -> Chart:
        match self:
            case ChartName.workflow:
                return WorkflowChart
            case ChartName.review:
                return ReviewChart


class MermaidDiagram(Value[str]):
    @staticmethod
    def fake() -> MermaidDiagram:
        return MermaidDiagram("stateDiagram-v2\n    direction LR\n    [*] --> grill\n")


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
            raise ValueError(
                f"{destination.root} has no extension, and the extension picks the image format."
            )
        return ImageFormat(suffix)


class MermaidFormat(Model):
    @staticmethod
    def fake() -> MermaidFormat:
        return MermaidFormat()


class DotSource(Value[str]):
    @staticmethod
    def fake() -> DotSource:
        return DotSource("digraph WorkflowChart {\n__initial_0 -> grill;\n}\n")

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


class ChartDiagram:
    @staticmethod
    def render_mermaid(chart: Chart) -> MermaidDiagram:
        return MermaidDiagram(MermaidGraphMachine(chart).get_mermaid())

    @staticmethod
    def render_dot(chart: Chart) -> DotSource:
        return DotSource(DotGraphMachine(chart).get_graph().to_string()).with_stable_ids()

    @staticmethod
    def write_image(chart: Chart, destination: DiagramPath, image_format: ImageFormat) -> None:
        graphs = pydot.graph_from_dot_data(ChartDiagram.render_dot(chart).root)
        if not graphs:
            raise ValueError("The chart's DOT source could not be parsed.")
        _ = graphs[0].write(str(destination.root), format=image_format.root)

    @staticmethod
    def write_mermaid(chart: Chart, destination: DiagramPath) -> None:
        _ = destination.root.write_text(MermaidDocument.of(ChartDiagram.render_mermaid(chart)).root)

    @staticmethod
    def write_diagram(chart: Chart, destination: DiagramPath) -> None:
        match ChartDiagram.format_of(destination):
            case MermaidFormat():
                ChartDiagram.write_mermaid(chart, destination)
            case ImageFormat() as image_format:
                ChartDiagram.write_image(chart, destination, image_format)

    @staticmethod
    def format_of(destination: DiagramPath) -> MermaidFormat | ImageFormat:
        if destination.root.suffix == ".md":
            return MermaidFormat()
        return ImageFormat.of(destination)

    @staticmethod
    def draw_diagram(chart_name: ChartName, destination: DiagramPath | None) -> ExitCode:
        chart = chart_name.to_chart()
        if destination is None:
            _ = sys.stdout.write(ChartDiagram.render_mermaid(chart).root)
            return ExitCode(0)
        try:
            ChartDiagram.write_diagram(chart, destination)
        except OSError as error:
            logger.error("Could not write %s: %s", destination.root, error)
            return ExitCode(1)
        except ValueError as error:
            logger.error("%s", error)
            return ExitCode(1)
        logger.info("Wrote %s", destination.root)
        return ExitCode(0)
