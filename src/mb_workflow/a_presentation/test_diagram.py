from pathlib import Path

import pytest

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
    assert render_mermaid().root.startswith("stateDiagram-v2\n    direction LR\n")


def test_the_diagram_shows_where_work_enters_and_ends() -> None:
    assert "    [*] --> grilling\n    merged --> [*]\n" in render_mermaid().root


def test_the_diagram_labels_a_state_by_the_name_the_chart_gives_it() -> None:
    assert '    state "QA" as qa\n' in render_mermaid().root


def test_the_diagram_labels_a_transition_with_the_event_that_causes_it() -> None:
    assert "    review --> implementing : resolve-review\n" in render_mermaid().root


def test_the_extension_of_the_destination_picks_the_image_format() -> None:
    assert ImageFormat.of(DiagramPath(Path("/tmp/flow.svg"))) == ImageFormat("svg")


def test_a_markdown_destination_is_written_as_mermaid() -> None:
    assert format_of(DiagramPath(Path("/tmp/flow.md"))) == MermaidFormat()


def test_an_image_destination_is_written_in_its_image_format() -> None:
    assert format_of(DiagramPath(Path("/tmp/flow.png"))) == ImageFormat("png")


def test_a_destination_with_no_extension_is_rejected() -> None:
    with pytest.raises(ValueError, match="no extension"):
        _ = format_of(DiagramPath(Path("/tmp/flow")))


def test_the_document_fences_the_diagram_as_mermaid() -> None:
    assert MermaidDocument.of(MermaidDiagram("stateDiagram-v2\n")) == MermaidDocument(
        "```mermaid\nstateDiagram-v2\n```\n"
    )


def test_the_fence_closes_on_its_own_line_when_the_diagram_has_no_trailing_newline() -> None:
    assert MermaidDocument.of(MermaidDiagram("stateDiagram-v2")) == MermaidDocument(
        "```mermaid\nstateDiagram-v2\n```\n"
    )


def test_the_document_keeps_the_chart_transitions() -> None:
    assert (
        "    review --> implementing : resolve-review\n"
        in MermaidDocument.of(render_mermaid()).root
    )


def test_the_image_source_is_the_same_on_every_render() -> None:
    assert render_dot() == render_dot()


def test_ids_derived_from_object_identity_are_numbered_in_order_of_appearance() -> None:
    source = DotSource(
        "__initial_4462144752 -> a;\ncluster___atomic_4462144752;\n__initial_987_sg;\n"
    )
    assert source.with_stable_ids() == DotSource(
        "__initial_0 -> a;\ncluster___atomic_0;\n__initial_1_sg;\n"
    )
