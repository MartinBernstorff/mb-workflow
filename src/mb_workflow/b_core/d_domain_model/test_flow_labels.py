from mb_workflow.b_core.d_domain_model.flow import WorkflowChart
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels, LabelGroupName
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
