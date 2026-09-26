import pytest

from mb_workflow.b_core.d_domain_model.flow import StateName, WorkflowChart
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels, LabelGroupName, state_of
from mb_workflow.b_core.d_domain_model.issue import LabelName, LabelNames

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


@pytest.mark.parametrize("state", ["Grilling", "Specced", "QA", "Merged"])
def test_a_flow_label_gives_the_state_of_its_name(state: str) -> None:
    held = LabelNames((LabelName("Backend"), LabelName(state)))
    assert state_of(WorkflowChart, held) == StateName(state)


def test_a_flow_label_in_another_case_gives_the_state_as_the_chart_spells_it() -> None:
    assert state_of(WorkflowChart, LabelNames((LabelName("implementing"),))) == StateName(
        "Implementing"
    )


def test_a_ticket_without_a_flow_label_counts_as_grilling() -> None:
    assert state_of(WorkflowChart, LabelNames((LabelName("Backend"),))) == StateName("Grilling")
