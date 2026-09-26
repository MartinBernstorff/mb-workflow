import pytest

from mb_workflow.b_core.d_domain_model.flow import FlowError, StateName, WorkflowChart
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels, state_of
from mb_workflow.b_core.d_domain_model.issue import (
    GroupedLabel,
    GroupedLabels,
    LabelGroupName,
    LabelName,
    LabelNames,
)

GRILLING = LabelName("Grilling")
QA = LabelName("QA")
MERGED = LabelName("Merged")


def flow_labels_of(*labels: LabelName) -> FlowLabels:
    return FlowLabels(group=LabelGroupName.fake(), labels=LabelNames(labels))


def test_every_state_of_the_chart_gets_a_label_in_chart_order() -> None:
    assert FlowLabels.of_chart(WorkflowChart, LabelGroupName.fake()).labels == LabelNames(
        tuple(
            LabelName(state)
            for state in (
                "Grilling",
                "Speccing",
                "Specced",
                "Implementing",
                "QA",
                "Review",
                "Merging",
                "Merged",
            )
        )
    )


def test_an_empty_group_misses_every_flow_label() -> None:
    wanted = FlowLabels.fake()
    assert wanted.missing(LabelNames(())) == wanted.labels


def test_a_full_group_misses_none() -> None:
    wanted = FlowLabels.fake()
    assert wanted.missing(wanted.labels) == LabelNames(())


def test_the_labels_the_group_lacks_are_missing() -> None:
    assert flow_labels_of(GRILLING, QA, MERGED).missing(LabelNames((QA,))) == LabelNames(
        (GRILLING, MERGED)
    )


def test_a_label_held_in_another_case_is_not_missing() -> None:
    assert flow_labels_of(QA).missing(LabelNames((LabelName("qa"),))) == LabelNames(())


def test_labels_outside_the_flow_do_not_count() -> None:
    assert flow_labels_of(QA).missing(LabelNames((LabelName("Blocked"), QA))) == LabelNames(())


def test_relabelling_adds_the_label_of_the_state() -> None:
    assert flow_labels_of(GRILLING, QA).relabelled(LabelNames(()), StateName("QA")) == LabelNames(
        (QA,)
    )


def test_relabelling_replaces_any_other_flow_label_and_keeps_the_rest() -> None:
    blocked = LabelName("Blocked")
    held = LabelNames((LabelName("grilling"), blocked))
    assert flow_labels_of(GRILLING, QA).relabelled(held, StateName("QA")) == LabelNames(
        (blocked, QA)
    )


def in_flow(*labels: LabelName) -> GroupedLabels:
    return GroupedLabels(
        tuple(GroupedLabel(group=LabelGroupName.fake(), label=label) for label in labels)
    )


@pytest.mark.parametrize("state", ["Grilling", "Specced", "QA", "Merged"])
def test_a_flow_label_gives_the_state_of_its_name(state: str) -> None:
    held = GroupedLabels(
        (
            GroupedLabel(group=LabelGroupName("team"), label=LabelName("Backend")),
            *in_flow(LabelName(state)).root,
        )
    )
    assert state_of(WorkflowChart, FlowLabels.fake(), held) == StateName(state)


def test_a_flow_label_in_another_case_gives_the_state_as_the_chart_spells_it() -> None:
    assert state_of(
        WorkflowChart, FlowLabels.fake(), in_flow(LabelName("implementing"))
    ) == StateName("Implementing")


def test_the_flow_group_is_found_whatever_its_case() -> None:
    held = GroupedLabels((GroupedLabel(group=LabelGroupName("Flow"), label=QA),))
    assert state_of(WorkflowChart, FlowLabels.fake(), held) == StateName("QA")


def test_a_ticket_without_a_flow_label_counts_as_grilling() -> None:
    assert state_of(WorkflowChart, FlowLabels.fake(), GroupedLabels(())) == StateName("Grilling")


def test_a_label_named_as_a_state_outside_the_flow_group_does_not_count() -> None:
    held = GroupedLabels((GroupedLabel(group=LabelGroupName("team"), label=QA),))
    assert state_of(WorkflowChart, FlowLabels.fake(), held) == StateName("Grilling")


def test_a_ticket_with_two_flow_labels_is_a_clear_error() -> None:
    with pytest.raises(FlowError, match="Grilling, QA"):
        _ = state_of(WorkflowChart, FlowLabels.fake(), in_flow(GRILLING, QA))


def test_a_flow_label_that_names_no_state_is_a_clear_error() -> None:
    with pytest.raises(FlowError, match="Marinating is no state of the chart"):
        _ = state_of(WorkflowChart, FlowLabels.fake(), in_flow(LabelName("Marinating")))
