from pathlib import Path

import pytest

from mb_workflow.a_presentation.diagram import DiagramPath, ImageFormat, render_mermaid


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


def test_a_destination_with_no_extension_is_rejected() -> None:
    with pytest.raises(ValueError, match="no extension"):
        _ = ImageFormat.of(DiagramPath(Path("/tmp/flow")))
