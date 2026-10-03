import re

import pytest
from safe_result import Err, Ok

from mb_workflow.b_core.d_domain_model.flow import FlowError, StateName, WorkflowChart
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
from mb_workflow.b_core.d_domain_model.issue import (
    ColoredLabel,
    ColoredLabels,
    GroupedLabel,
    GroupedLabels,
    LabelColor,
    LabelGroupName,
    LabelName,
    LabelNames,
)

GRILLING = LabelName("Grilling")
QA = LabelName("QA")
MERGED = LabelName("Merged")


def flow_labels_of(*labels: LabelName) -> FlowLabels:
    return FlowLabels(group=LabelGroupName.fake(), labels=LabelNames(labels), entry=LabelNames(()))


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


def test_the_chart_marks_grilling_speccing_and_specced_as_entry_labels() -> None:
    entry = LabelNames((GRILLING, LabelName("Speccing"), LabelName("Specced")))
    assert FlowLabels.fake().entry == entry


def test_an_entry_label_is_colored_yellow() -> None:
    assert FlowLabels.fake().colored(LabelNames((GRILLING,))) == ColoredLabels(
        (ColoredLabel(name=GRILLING, color=LabelColor.yellow()),)
    )


def test_any_other_flow_label_is_colored_grey() -> None:
    assert FlowLabels.fake().colored(LabelNames((QA,))) == ColoredLabels(
        (ColoredLabel(name=QA, color=LabelColor.grey()),)
    )


def test_a_flow_label_held_in_the_wrong_color_is_miscolored() -> None:
    held = ColoredLabels(
        (
            ColoredLabel(name=GRILLING, color=LabelColor.yellow()),
            ColoredLabel(name=QA, color=LabelColor.yellow()),
        )
    )
    assert FlowLabels.fake().miscolored(held) == LabelNames((QA,))


def test_a_color_written_in_another_case_is_not_miscolored() -> None:
    held = ColoredLabels(
        (ColoredLabel(name=GRILLING, color=LabelColor(LabelColor.yellow().root.upper())),)
    )
    assert FlowLabels.fake().miscolored(held) == LabelNames(())


def test_labels_outside_the_flow_are_never_miscolored() -> None:
    held = ColoredLabels((ColoredLabel(name=LabelName("Blocked"), color=LabelColor.yellow()),))
    assert FlowLabels.fake().miscolored(held) == LabelNames(())


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
    assert FlowLabels.fake().state_of(WorkflowChart, held) == Ok(StateName(state))


def test_a_flow_label_in_another_case_gives_the_state_as_the_chart_spells_it() -> None:
    assert FlowLabels.fake().state_of(WorkflowChart, in_flow(LabelName("implementing"))) == Ok(
        StateName("Implementing")
    )


def test_the_flow_group_is_found_whatever_its_case() -> None:
    held = GroupedLabels((GroupedLabel(group=LabelGroupName("Flow"), label=QA),))
    assert FlowLabels.fake().state_of(WorkflowChart, held) == Ok(StateName("QA"))


def test_a_ticket_without_a_flow_label_has_no_state() -> None:
    assert FlowLabels.fake().state_of(WorkflowChart, GroupedLabels(())) == Ok(None)


def test_a_label_named_as_a_state_outside_the_flow_group_does_not_count() -> None:
    held = GroupedLabels((GroupedLabel(group=LabelGroupName("team"), label=QA),))
    assert FlowLabels.fake().state_of(WorkflowChart, held) == Ok(None)


def test_a_ticket_with_two_flow_labels_is_a_clear_error() -> None:
    refused = FlowLabels.fake().state_of(WorkflowChart, in_flow(GRILLING, QA))
    assert isinstance(refused, Err)
    assert isinstance(refused.error, FlowError)
    assert re.search("Grilling, QA", str(refused.error))


def test_a_flow_label_that_names_no_state_is_a_clear_error() -> None:
    refused = FlowLabels.fake().state_of(WorkflowChart, in_flow(LabelName("Marinating")))
    assert isinstance(refused, Err)
    assert isinstance(refused.error, FlowError)
    assert re.search("Marinating is no state of the chart", str(refused.error))
