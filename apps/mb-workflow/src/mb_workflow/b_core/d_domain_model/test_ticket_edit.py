import pytest
from safe_result import Err, Ok

from mb_workflow.b_core.d_domain_model.flow import StateName, UnknownStateError
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
from mb_workflow.b_core.d_domain_model.issue import (
    Assignee,
    Cleared,
    Issue,
    IssueDescription,
    IssueDetail,
    IssueIdentifier,
    IssueStatusName,
    IssueUpdate,
    LabelName,
    LabelNames,
    Milestone,
    MilestoneName,
    ProjectName,
)
from mb_workflow.b_core.d_domain_model.ticket_edit import (
    RemoveMilestone,
    TicketEdit,
    TicketEditError,
)
from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses


def held(issue: Issue) -> IssueDetail:
    return IssueDetail.fake().model_copy(update={"issue": issue})


def viewer() -> Assignee:
    return Assignee("viewer@flowbase.io")


def test_an_empty_edit_is_refused() -> None:
    refused = TicketEdit.nothing().checked(FlowLabels.fake())
    assert isinstance(refused, Err)
    assert isinstance(refused.error, TicketEditError)


def test_a_title_edit_changes_only_the_title() -> None:
    assert TicketEdit.fake().update(
        IssueDetail.fake(), viewer(), FlowLabels.fake(), TicketStatuses.fake()
    ) == IssueUpdate.nothing().model_copy(update={"title": TicketEdit.fake().title})


def test_the_body_becomes_the_description() -> None:
    body = IssueDescription("New body.")
    edit = TicketEdit.nothing().model_copy(update={"body": body})
    assert (
        edit.update(
            IssueDetail.fake(), viewer(), FlowLabels.fake(), TicketStatuses.fake()
        ).description
        == body
    )


def test_the_body_file_becomes_the_description() -> None:
    body_file = IssueDescription("From file.")
    edit = TicketEdit.nothing().model_copy(update={"body_file": body_file})
    assert (
        edit.update(
            IssueDetail.fake(), viewer(), FlowLabels.fake(), TicketStatuses.fake()
        ).description
        == body_file
    )


def test_a_body_and_a_body_file_together_are_refused() -> None:
    edit = TicketEdit.nothing().model_copy(
        update={"body": IssueDescription("a"), "body_file": IssueDescription("b")}
    )
    refused = edit.checked(FlowLabels.fake())
    assert isinstance(refused, Err)
    assert isinstance(refused.error, TicketEditError)


def test_added_labels_join_the_held_ones() -> None:
    backend = LabelName("Backend")
    edit = TicketEdit.nothing().model_copy(update={"add_labels": LabelNames((backend,))})
    assert edit.update(
        IssueDetail.fake(), viewer(), FlowLabels.fake(), TicketStatuses.fake()
    ).labels == LabelNames((LabelName.fake(), backend))


def test_adding_a_held_label_in_another_case_carries_it_once() -> None:
    edit = TicketEdit.nothing().model_copy(
        update={"add_labels": LabelNames((LabelName("D-IMPLEMENT"),))}
    )
    assert (
        edit.update(IssueDetail.fake(), viewer(), FlowLabels.fake(), TicketStatuses.fake()).labels
        == LabelNames.fake()
    )


def test_a_removed_label_is_dropped_whatever_its_case() -> None:
    edit = TicketEdit.nothing().model_copy(
        update={"remove_labels": LabelNames((LabelName("D-IMPLEMENT"),))}
    )
    assert edit.update(
        IssueDetail.fake(), viewer(), FlowLabels.fake(), TicketStatuses.fake()
    ).labels == LabelNames(())


def test_labels_are_left_alone_unless_named() -> None:
    assert (
        TicketEdit.fake()
        .update(IssueDetail.fake(), viewer(), FlowLabels.fake(), TicketStatuses.fake())
        .labels
        is None
    )


def test_adding_an_assignee_replaces_the_held_one() -> None:
    other = Assignee("other@flowbase.io")
    edit = TicketEdit.nothing().model_copy(update={"add_assignee": other})
    assert (
        edit.update(IssueDetail.fake(), viewer(), FlowLabels.fake(), TicketStatuses.fake()).assignee
        == other
    )


def test_me_resolves_to_the_viewer() -> None:
    edit = TicketEdit.nothing().model_copy(update={"add_assignee": Assignee.me()})
    assert (
        edit.update(IssueDetail.fake(), viewer(), FlowLabels.fake(), TicketStatuses.fake()).assignee
        == viewer()
    )


def test_removing_the_held_assignee_clears_it() -> None:
    current = IssueDetail.fake().model_copy(update={"assignee": viewer()})
    edit = TicketEdit.nothing().model_copy(update={"remove_assignee": Assignee.me()})
    assert (
        edit.update(current, viewer(), FlowLabels.fake(), TicketStatuses.fake()).assignee
        == Cleared()
    )


def test_removing_someone_not_assigned_leaves_the_assignee() -> None:
    current = IssueDetail.fake().model_copy(update={"assignee": viewer()})
    edit = TicketEdit.nothing().model_copy(
        update={"remove_assignee": Assignee("other@flowbase.io")}
    )
    assert edit.update(current, viewer(), FlowLabels.fake(), TicketStatuses.fake()).assignee is None


def test_adding_a_project_moves_the_issue() -> None:
    other = ProjectName("Other")
    edit = TicketEdit.nothing().model_copy(update={"add_project": other})
    assert (
        edit.update(IssueDetail.fake(), viewer(), FlowLabels.fake(), TicketStatuses.fake()).project
        == other
    )


def test_removing_the_held_project_clears_it_whatever_its_case() -> None:
    edit = TicketEdit.nothing().model_copy(
        update={"remove_project": ProjectName(ProjectName.fake().root.upper())}
    )
    assert (
        edit.update(IssueDetail.fake(), viewer(), FlowLabels.fake(), TicketStatuses.fake()).project
        == Cleared()
    )


def test_removing_another_project_leaves_the_project() -> None:
    edit = TicketEdit.nothing().model_copy(update={"remove_project": ProjectName("Other")})
    assert (
        edit.update(IssueDetail.fake(), viewer(), FlowLabels.fake(), TicketStatuses.fake()).project
        is None
    )


def test_a_milestone_is_looked_up_in_the_held_project() -> None:
    edit = TicketEdit.nothing().model_copy(update={"milestone": MilestoneName.fake()})
    assert (
        edit.update(
            IssueDetail.fake(), viewer(), FlowLabels.fake(), TicketStatuses.fake()
        ).milestone
        == Milestone.fake()
    )


def test_a_milestone_is_looked_up_in_the_project_being_moved_to() -> None:
    other = ProjectName("Other")
    edit = TicketEdit.nothing().model_copy(
        update={"add_project": other, "milestone": MilestoneName.fake()}
    )
    assert edit.update(
        IssueDetail.fake(), viewer(), FlowLabels.fake(), TicketStatuses.fake()
    ).milestone == Milestone(project=other, name=MilestoneName.fake())


def test_a_milestone_without_a_project_is_refused() -> None:
    edit = TicketEdit.nothing().model_copy(update={"milestone": MilestoneName.fake()})
    with pytest.raises(TicketEditError):
        _ = edit.update(
            held(Issue.fake().model_copy(update={"project": None})),
            viewer(),
            FlowLabels.fake(),
            TicketStatuses.fake(),
        )


def test_removing_the_milestone_clears_it() -> None:
    edit = TicketEdit.nothing().model_copy(update={"remove_milestone": RemoveMilestone(True)})
    assert (
        edit.update(
            IssueDetail.fake(), viewer(), FlowLabels.fake(), TicketStatuses.fake()
        ).milestone
        == Cleared()
    )


def test_setting_and_removing_the_milestone_together_are_refused() -> None:
    edit = TicketEdit.nothing().model_copy(
        update={"milestone": MilestoneName.fake(), "remove_milestone": RemoveMilestone(True)}
    )
    refused = edit.checked(FlowLabels.fake())
    assert isinstance(refused, Err)
    assert isinstance(refused.error, TicketEditError)


def test_label_flags_split_on_commas() -> None:
    flags = LabelNames((LabelName("Backend, d-grill"), LabelName("d-implement")))
    assert flags.split() == LabelNames(
        (LabelName("Backend"), LabelName("d-grill"), LabelName("d-implement"))
    )


def test_a_state_sets_its_flow_label_and_status() -> None:
    review = LabelName("Review")
    in_review = IssueStatusName("In Review")
    edit = TicketEdit.nothing().model_copy(update={"state": StateName(review.root)})
    update = edit.update(IssueDetail.fake(), viewer(), FlowLabels.fake(), TicketStatuses.fake())
    assert (update.labels, update.status) == (LabelNames((LabelName.fake(), review)), in_review)


def test_a_state_is_spelled_as_the_chart_spells_it() -> None:
    review = StateName("Review")
    edit = TicketEdit.nothing().model_copy(update={"state": StateName("rEVIEW")})
    assert edit.checked(FlowLabels.fake()).unwrap().state == review


def test_an_unknown_state_is_refused() -> None:
    edit = TicketEdit.nothing().model_copy(update={"state": StateName("Nowhere")})
    refused = edit.checked(FlowLabels.fake())
    assert isinstance(refused, Err)
    assert isinstance(refused.error, UnknownStateError)


@pytest.mark.parametrize("option", ["add_labels", "remove_labels"])
def test_a_flow_label_in_a_label_option_is_refused(option: str) -> None:
    edit = TicketEdit.nothing().model_copy(update={option: LabelNames((LabelName("specced"),))})
    state_option = "--state"
    refused = edit.checked(FlowLabels.fake())
    assert isinstance(refused, Err)
    assert state_option in str(refused.error)


def test_an_edit_with_only_relations_is_accepted() -> None:
    edit = TicketEdit.nothing().model_copy(update={"add_blocks": (IssueIdentifier("E-1"),)})
    assert isinstance(edit.checked(FlowLabels.fake()), Ok)


def test_added_relations_carry_into_the_update() -> None:
    edit = TicketEdit.nothing().model_copy(
        update={
            "add_blocks": (IssueIdentifier("E-1"),),
            "add_blocked_by": (IssueIdentifier("E-2"),),
        }
    )
    update = edit.update(IssueDetail.fake(), viewer(), FlowLabels.fake(), TicketStatuses.fake())
    assert (update.blocks, update.blocked_by) == (
        (IssueIdentifier("E-1"),),
        (IssueIdentifier("E-2"),),
    )


def test_relations_the_ticket_already_holds_are_not_added_again() -> None:
    current = IssueDetail.fake().model_copy(
        update={
            "blocks": frozenset({IssueIdentifier("E-1")}),
            "blocked_by": frozenset({IssueIdentifier("E-2")}),
        }
    )
    edit = TicketEdit.nothing().model_copy(
        update={
            "add_blocks": (IssueIdentifier("E-1"), IssueIdentifier("E-3")),
            "add_blocked_by": (IssueIdentifier("E-2"),),
        }
    )
    update = edit.update(current, viewer(), FlowLabels.fake(), TicketStatuses.fake())
    assert (update.blocks, update.blocked_by) == ((IssueIdentifier("E-3"),), ())
