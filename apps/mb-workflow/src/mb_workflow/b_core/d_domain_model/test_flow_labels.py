import pytest
from assertions import Assert
from safe_result import Ok

from mb_workflow.b_core.d_domain_model.flow import FlowError, StateName, WorkflowChart
from mb_workflow.b_core.d_domain_model.flow_labels import (
    FlowLabels,
    GroupSync,
    LabelRename,
    LabelRenames,
)
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

GRILL = LabelName("grill")
QA = LabelName("qa")
MERGED = LabelName("merged")


def flow_labels_of(*labels: LabelName) -> FlowLabels:
    return FlowLabels(
        group=LabelGroupName.fake(),
        labels=LabelNames(labels),
        entry=LabelNames(()),
        former=LabelRenames(()),
    )


def test_every_state_of_the_chart_gets_a_label_in_chart_order() -> None:
    Assert.that(
        FlowLabels.of_chart(WorkflowChart, LabelGroupName.fake(), LabelRenames(())).labels
    ).matches(
        LabelNames(
            tuple(
                LabelName(state)
                for state in (
                    "grill",
                    "to-ticket",
                    "todo",
                    "implementing",
                    "qa",
                    "review",
                    "merging",
                    "merged",
                )
            )
        )
    )


def test_the_chart_marks_grill_to_ticket_and_todo_as_entry_labels() -> None:
    entry = LabelNames((GRILL, LabelName("to-ticket"), LabelName("todo")))
    Assert.that(FlowLabels.fake().entry).matches(entry)


def test_an_entry_label_is_colored_yellow() -> None:
    Assert.that(FlowLabels.fake().colored(LabelNames((GRILL,)))).matches(
        ColoredLabels((ColoredLabel(name=GRILL, color=LabelColor.yellow()),))
    )


def test_any_other_flow_label_is_colored_grey() -> None:
    Assert.that(FlowLabels.fake().colored(LabelNames((QA,)))).matches(
        ColoredLabels((ColoredLabel(name=QA, color=LabelColor.grey()),))
    )


def test_a_flow_label_held_in_the_wrong_color_is_miscolored() -> None:
    held = ColoredLabels(
        (
            ColoredLabel(name=GRILL, color=LabelColor.yellow()),
            ColoredLabel(name=QA, color=LabelColor.yellow()),
        )
    )
    Assert.that(FlowLabels.fake().miscolored(held)).matches(LabelNames((QA,)))


def test_a_color_written_in_another_case_is_not_miscolored() -> None:
    held = ColoredLabels(
        (ColoredLabel(name=GRILL, color=LabelColor(LabelColor.yellow().root.upper())),)
    )
    Assert.that(FlowLabels.fake().miscolored(held)).matches(LabelNames(()))


def test_labels_outside_the_flow_are_never_miscolored() -> None:
    held = ColoredLabels((ColoredLabel(name=LabelName("Blocked"), color=LabelColor.yellow()),))
    Assert.that(FlowLabels.fake().miscolored(held)).matches(LabelNames(()))


def test_an_empty_group_misses_every_flow_label() -> None:
    wanted = FlowLabels.fake()
    Assert.that(wanted.missing(LabelNames(()))).matches(wanted.labels)


def test_a_full_group_misses_none() -> None:
    wanted = FlowLabels.fake()
    Assert.that(wanted.missing(wanted.labels)).matches(LabelNames(()))


def test_the_labels_the_group_lacks_are_missing() -> None:
    Assert.that(flow_labels_of(GRILL, QA, MERGED).missing(LabelNames((QA,)))).matches(
        LabelNames((GRILL, MERGED))
    )


def test_a_label_held_in_another_case_is_not_missing() -> None:
    Assert.that(flow_labels_of(QA).missing(LabelNames((LabelName("QA"),)))).matches(LabelNames(()))


def test_labels_outside_the_flow_do_not_count() -> None:
    Assert.that(flow_labels_of(QA).missing(LabelNames((LabelName("Blocked"), QA)))).matches(
        LabelNames(())
    )


def grey(*labels: LabelName) -> ColoredLabels:
    return ColoredLabels(
        tuple(ColoredLabel(name=label, color=LabelColor.grey()) for label in labels)
    )


def test_a_group_matching_the_spec_needs_no_sync() -> None:
    Assert.that(flow_labels_of(QA, MERGED).sync_plan(grey(QA, MERGED))).matches(
        GroupSync.unchanged()
    )


def test_a_flow_label_spelled_in_another_case_is_renamed_to_the_spec() -> None:
    held = LabelName("QA")
    synced = flow_labels_of(QA).sync_plan(grey(held))
    Assert.that(synced.renamed).matches(LabelRenames((LabelRename(held=held, renamed=QA),)))


def test_a_flow_label_spelled_as_the_spec_is_not_renamed() -> None:
    Assert.that(flow_labels_of(QA).sync_plan(grey(QA)).renamed).matches(LabelRenames(()))


def test_a_label_outside_the_spec_is_deleted() -> None:
    obsolete = LabelName("Obsolete")
    Assert.that(flow_labels_of(QA).sync_plan(grey(QA, obsolete)).deleted).matches(
        LabelNames((obsolete,))
    )


def test_a_renamed_label_is_not_deleted() -> None:
    Assert.that(flow_labels_of(QA).sync_plan(grey(LabelName("QA"))).deleted).matches(LabelNames(()))


def renaming(former: LabelName, current: LabelName) -> FlowLabels:
    return flow_labels_of(current).model_copy(
        update={"former": LabelRenames((LabelRename(held=former, renamed=current),))}
    )


def test_a_former_flow_label_is_renamed_to_its_current_name() -> None:
    former = LabelName("Grilling")
    synced = renaming(former, GRILL).sync_plan(grey(former))
    Assert.that(synced.renamed).matches(LabelRenames((LabelRename(held=former, renamed=GRILL),)))
    Assert.that(synced.deleted).matches(LabelNames(()))


def test_a_former_flow_label_in_another_case_is_renamed_to_its_current_name() -> None:
    former, held = LabelName("Grilling"), LabelName("grilling")
    synced = renaming(former, GRILL).sync_plan(grey(held))
    Assert.that(synced.renamed).matches(LabelRenames((LabelRename(held=held, renamed=GRILL),)))


def test_a_former_flow_label_is_deleted_when_its_current_name_is_held() -> None:
    former = LabelName("Grilling")
    synced = renaming(former, GRILL).sync_plan(grey(former, GRILL))
    Assert.that(synced.renamed).matches(LabelRenames(()))
    Assert.that(synced.deleted).matches(LabelNames((former,)))


def test_a_former_flow_label_counts_as_its_current_name() -> None:
    former = LabelName("Grilling")
    Assert.that(renaming(former, GRILL).missing(LabelNames((former,)))).matches(LabelNames(()))


def test_the_chart_renames_the_former_entry_labels() -> None:
    Assert.that(FlowLabels.fake().former).matches(
        LabelRenames(
            tuple(
                LabelRename(held=LabelName(held), renamed=LabelName(renamed))
                for held, renamed in (
                    ("Grilling", "grill"),
                    ("Speccing", "to-ticket"),
                    ("Specced", "todo"),
                )
            )
        )
    )


def test_a_label_in_the_wrong_color_is_recolored_under_its_spec_name() -> None:
    held = ColoredLabels((ColoredLabel(name=LabelName("Grill"), color=LabelColor.grey()),))
    synced = FlowLabels.fake().sync_plan(held)
    Assert.that(synced.recolored).matches(LabelNames((GRILL,)))


def test_relabelling_adds_the_label_of_the_state() -> None:
    Assert.that(flow_labels_of(GRILL, QA).relabelled(LabelNames(()), StateName("qa"))).matches(
        LabelNames((QA,))
    )


def test_relabelling_replaces_any_other_flow_label_and_keeps_the_rest() -> None:
    blocked = LabelName("Blocked")
    held = LabelNames((LabelName("Grill"), blocked))
    Assert.that(flow_labels_of(GRILL, QA).relabelled(held, StateName("qa"))).matches(
        LabelNames((blocked, QA))
    )


def in_flow(*labels: LabelName) -> GroupedLabels:
    return GroupedLabels(
        tuple(GroupedLabel(group=LabelGroupName.fake(), label=label) for label in labels)
    )


@pytest.mark.parametrize("state", ["grill", "todo", "qa", "merged"])
def test_a_flow_label_gives_the_state_of_its_name(state: str) -> None:
    held = GroupedLabels(
        (
            GroupedLabel(group=LabelGroupName("team"), label=LabelName("Backend")),
            *in_flow(LabelName(state)).root,
        )
    )
    Assert.that(FlowLabels.fake().state_of(WorkflowChart, held)).matches(Ok(StateName(state)))


def test_a_flow_label_in_another_case_gives_the_state_as_the_chart_spells_it() -> None:
    Assert.that(
        FlowLabels.fake().state_of(WorkflowChart, in_flow(LabelName("Implementing")))
    ).matches(Ok(StateName("implementing")))


def test_the_flow_group_is_found_whatever_its_case() -> None:
    held = GroupedLabels((GroupedLabel(group=LabelGroupName("Flow"), label=QA),))
    Assert.that(FlowLabels.fake().state_of(WorkflowChart, held)).matches(Ok(StateName("qa")))


def test_a_ticket_without_a_flow_label_has_no_state() -> None:
    Assert.that(FlowLabels.fake().state_of(WorkflowChart, GroupedLabels(()))).matches(Ok(None))


def test_a_label_named_as_a_state_outside_the_flow_group_does_not_count() -> None:
    held = GroupedLabels((GroupedLabel(group=LabelGroupName("team"), label=QA),))
    Assert.that(FlowLabels.fake().state_of(WorkflowChart, held)).matches(Ok(None))


def test_a_ticket_with_two_flow_labels_is_a_clear_error() -> None:
    refused = FlowLabels.fake().state_of(WorkflowChart, in_flow(GRILL, QA))
    error = Assert.that(refused.error).is_instance(FlowError)
    Assert.that(str(error)).matches_pattern("grill, qa")


def test_a_flow_label_that_names_no_state_is_a_clear_error() -> None:
    refused = FlowLabels.fake().state_of(WorkflowChart, in_flow(LabelName("Marinating")))
    error = Assert.that(refused.error).is_instance(FlowError)
    Assert.that(str(error)).matches_pattern("Marinating is no state of the chart")
