from pathlib import Path

import pytest
from statemachine.exceptions import TransitionNotAllowed

from mb_workflow.flow import (
    DiagramPath,
    Edge,
    Edges,
    EventName,
    ImageFormat,
    Stage,
    Stages,
    WorkflowChart,
    render_mermaid,
    write_image,
)


def edge(source: Stage, name: EventName, target: Stage) -> Edge:
    return Edge(source=source, event=name, target=target)


def test_the_chart_holds_every_stage_the_work_passes_through() -> None:
    assert Stages.of_chart() == Stages(frozenset(Stage))


def test_work_enters_the_chart_at_grilling() -> None:
    assert Stages.start() == Stage.grilling


def test_the_chart_holds_every_transition_the_work_can_take() -> None:
    assert Edges.of_chart() == Edges(
        frozenset(
            {
                edge(Stage.grilling, EventName("to-ticket"), Stage.speccing),
                edge(Stage.speccing, EventName("specced"), Stage.specced),
                edge(Stage.specced, EventName("implement"), Stage.implementing),
                edge(Stage.implementing, EventName("qa"), Stage.qa),
                edge(Stage.implementing, EventName("grill"), Stage.grilling),
                edge(Stage.implementing, EventName("to-ticket"), Stage.speccing),
                edge(Stage.qa, EventName("implement"), Stage.implementing),
                edge(Stage.qa, EventName("ready"), Stage.review),
                edge(Stage.qa, EventName("merge"), Stage.merging),
                edge(Stage.review, EventName("resolve-review"), Stage.implementing),
                edge(Stage.review, EventName("qa"), Stage.qa),
                edge(Stage.review, EventName("merge"), Stage.merging),
                edge(Stage.review, EventName("merged"), Stage.merged),
                edge(Stage.merging, EventName("merged"), Stage.merged),
            }
        )
    )


def test_an_event_with_no_transition_from_the_current_stage_raises() -> None:
    with pytest.raises(TransitionNotAllowed):
        WorkflowChart().send(EventName("merge").root)


def test_an_event_the_chart_has_never_heard_of_raises() -> None:
    with pytest.raises(TransitionNotAllowed):
        WorkflowChart().send(EventName("abandon").root)


def test_an_exception_raised_during_a_transition_propagates() -> None:
    class Detonator:
        def on_transition(self) -> None:
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        WorkflowChart(listeners=[Detonator()]).send(EventName("to-ticket").root)


def test_renders_the_chart_as_a_mermaid_state_diagram() -> None:
    assert render_mermaid().root == (
        "stateDiagram-v2\n"
        "    direction LR\n"
        '    state "Grilling" as grilling\n'
        '    state "Speccing" as speccing\n'
        '    state "Specced" as specced\n'
        '    state "Implementing" as implementing\n'
        '    state "QA" as qa\n'
        '    state "Review" as review\n'
        '    state "Merging" as merging\n'
        '    state "Merged" as merged\n'
        "    [*] --> grilling\n"
        "    merged --> [*]\n"
        "    grilling --> speccing : to-ticket\n"
        "    speccing --> specced : specced\n"
        "    specced --> implementing : implement\n"
        "    implementing --> grilling : grill\n"
        "    implementing --> speccing : to-ticket\n"
        "    implementing --> qa : qa\n"
        "    qa --> implementing : implement\n"
        "    qa --> review : ready\n"
        "    qa --> merging : merge\n"
        "    review --> qa : qa\n"
        "    review --> merging : merge\n"
        "    review --> merged : merged\n"
        "    review --> implementing : resolve-review\n"
        "    merging --> merged : merged\n"
    )


def test_the_extension_of_the_destination_picks_the_image_format() -> None:
    assert ImageFormat.of(DiagramPath(Path("/tmp/flow.svg"))) == ImageFormat("svg")


def test_a_destination_with_no_extension_is_rejected() -> None:
    with pytest.raises(ValueError, match="no extension"):
        _ = ImageFormat.of(DiagramPath(Path("/tmp/flow")))


def test_writes_the_chart_to_an_image_file(tmp_path: Path) -> None:
    destination = DiagramPath(tmp_path / "flow.png")
    write_image(destination)
    assert destination.root.read_bytes()[:4] == b"\x89PNG"


def test_an_extension_graphviz_does_not_know_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not know"):
        write_image(DiagramPath(tmp_path / "flow.bogus"))
