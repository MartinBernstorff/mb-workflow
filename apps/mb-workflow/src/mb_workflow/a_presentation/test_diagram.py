from pathlib import Path

import pytest
from assertions import Assert

from mb_workflow.a_presentation.diagram import (
    DiagramPath,
    DotSource,
    ImageFormat,
    MermaidDiagram,
    MermaidDocument,
    MermaidFormat,
    format_of,
    render_dot,
    render_mermaid,
)


def test_renders_a_mermaid_state_diagram() -> None:
    Assert.that(render_mermaid().root).matches_pattern(r"^stateDiagram-v2\n    direction LR\n")


def test_the_diagram_shows_where_work_enters_and_ends() -> None:
    Assert.that(render_mermaid().root).contains("    [*] --> grill\n    merged --> [*]\n")


def test_the_diagram_labels_a_state_by_the_name_the_chart_gives_it() -> None:
    Assert.that(render_mermaid().root).contains('    state "to-ticket" as to_ticket\n')


def test_the_diagram_labels_a_transition_with_the_event_that_causes_it() -> None:
    Assert.that(render_mermaid().root).contains("    review --> implementing : resolve-review\n")


def test_the_extension_of_the_destination_picks_the_image_format() -> None:
    Assert.that(ImageFormat.of(DiagramPath(Path("/tmp/flow.svg")))).matches(ImageFormat("svg"))


def test_a_markdown_destination_is_written_as_mermaid() -> None:
    Assert.that(format_of(DiagramPath(Path("/tmp/flow.md")))).matches(MermaidFormat())


def test_an_image_destination_is_written_in_its_image_format() -> None:
    Assert.that(format_of(DiagramPath(Path("/tmp/flow.png")))).matches(ImageFormat("png"))


def test_a_destination_with_no_extension_is_rejected() -> None:
    with pytest.raises(ValueError, match="no extension"):
        _ = format_of(DiagramPath(Path("/tmp/flow")))


def test_the_document_fences_the_diagram_as_mermaid() -> None:
    Assert.that(MermaidDocument.of(MermaidDiagram("stateDiagram-v2\n"))).matches(
        MermaidDocument("```mermaid\nstateDiagram-v2\n```\n")
    )


def test_the_fence_closes_on_its_own_line_when_the_diagram_has_no_trailing_newline() -> None:
    Assert.that(MermaidDocument.of(MermaidDiagram("stateDiagram-v2"))).matches(
        MermaidDocument("```mermaid\nstateDiagram-v2\n```\n")
    )


def test_the_document_keeps_the_chart_transitions() -> None:
    Assert.that(MermaidDocument.of(render_mermaid()).root).contains(
        "    review --> implementing : resolve-review\n"
    )


def test_the_image_source_is_the_same_on_every_render() -> None:
    Assert.that(render_dot()).matches(render_dot())


def test_ids_derived_from_object_identity_are_numbered_in_order_of_appearance() -> None:
    source = DotSource(
        "__initial_4462144752 -> a;\ncluster___atomic_4462144752;\n__initial_987_sg;\n"
    )
    Assert.that(source.with_stable_ids()).matches(
        DotSource("__initial_0 -> a;\ncluster___atomic_0;\n__initial_1_sg;\n")
    )
