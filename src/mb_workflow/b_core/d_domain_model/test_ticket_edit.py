import pytest

from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
from mb_workflow.b_core.d_domain_model.issue import (
    Assignee,
    Cleared,
    Issue,
    IssueDescription,
    IssueDetail,
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


def held(issue: Issue) -> IssueDetail:
    return IssueDetail.fake().model_copy(update={"issue": issue})


def viewer() -> Assignee:
    return Assignee("viewer@flowbase.io")


def test_an_empty_edit_is_refused() -> None:
    with pytest.raises(TicketEditError):
        _ = TicketEdit.nothing().checked(FlowLabels.fake())


def test_a_title_edit_changes_only_the_title() -> None:
    assert TicketEdit.fake().update(
        IssueDetail.fake(), viewer()
    ) == IssueUpdate.nothing().model_copy(update={"title": TicketEdit.fake().title})


def test_the_body_becomes_the_description() -> None:
    edit = TicketEdit.nothing().model_copy(update={"body": IssueDescription("New body.")})
    assert edit.update(IssueDetail.fake(), viewer()).description == IssueDescription("New body.")


def test_the_body_file_becomes_the_description() -> None:
    edit = TicketEdit.nothing().model_copy(update={"body_file": IssueDescription("From file.")})
    assert edit.update(IssueDetail.fake(), viewer()).description == IssueDescription("From file.")


def test_a_body_and_a_body_file_together_are_refused() -> None:
    edit = TicketEdit.nothing().model_copy(
        update={"body": IssueDescription("a"), "body_file": IssueDescription("b")}
    )
    with pytest.raises(TicketEditError):
        _ = edit.checked(FlowLabels.fake())


def test_added_labels_join_the_held_ones() -> None:
    edit = TicketEdit.nothing().model_copy(
        update={"add_labels": LabelNames((LabelName("Backend"),))}
    )
    assert edit.update(IssueDetail.fake(), viewer()).labels == LabelNames(
        (LabelName.fake(), LabelName("Backend"))
    )


def test_adding_a_held_label_in_another_case_carries_it_once() -> None:
    edit = TicketEdit.nothing().model_copy(
        update={"add_labels": LabelNames((LabelName("D-IMPLEMENT"),))}
    )
    assert edit.update(IssueDetail.fake(), viewer()).labels == LabelNames.fake()


def test_a_removed_label_is_dropped_whatever_its_case() -> None:
    edit = TicketEdit.nothing().model_copy(
        update={"remove_labels": LabelNames((LabelName("D-IMPLEMENT"),))}
    )
    assert edit.update(IssueDetail.fake(), viewer()).labels == LabelNames(())


def test_labels_are_left_alone_unless_named() -> None:
    assert TicketEdit.fake().update(IssueDetail.fake(), viewer()).labels is None


def test_adding_an_assignee_replaces_the_held_one() -> None:
    edit = TicketEdit.nothing().model_copy(update={"add_assignee": Assignee("other@flowbase.io")})
    assert edit.update(IssueDetail.fake(), viewer()).assignee == Assignee("other@flowbase.io")


def test_me_resolves_to_the_viewer() -> None:
    edit = TicketEdit.nothing().model_copy(update={"add_assignee": Assignee.me()})
    assert edit.update(IssueDetail.fake(), viewer()).assignee == viewer()


def test_removing_the_held_assignee_clears_it() -> None:
    current = IssueDetail.fake().model_copy(update={"assignee": viewer()})
    edit = TicketEdit.nothing().model_copy(update={"remove_assignee": Assignee.me()})
    assert edit.update(current, viewer()).assignee == Cleared()


def test_removing_someone_not_assigned_leaves_the_assignee() -> None:
    current = IssueDetail.fake().model_copy(update={"assignee": viewer()})
    edit = TicketEdit.nothing().model_copy(
        update={"remove_assignee": Assignee("other@flowbase.io")}
    )
    assert edit.update(current, viewer()).assignee is None


def test_adding_a_project_moves_the_issue() -> None:
    edit = TicketEdit.nothing().model_copy(update={"add_project": ProjectName("Other")})
    assert edit.update(IssueDetail.fake(), viewer()).project == ProjectName("Other")


def test_removing_the_held_project_clears_it_whatever_its_case() -> None:
    edit = TicketEdit.nothing().model_copy(
        update={"remove_project": ProjectName(ProjectName.fake().root.upper())}
    )
    assert edit.update(IssueDetail.fake(), viewer()).project == Cleared()


def test_removing_another_project_leaves_the_project() -> None:
    edit = TicketEdit.nothing().model_copy(update={"remove_project": ProjectName("Other")})
    assert edit.update(IssueDetail.fake(), viewer()).project is None


def test_a_milestone_is_looked_up_in_the_held_project() -> None:
    edit = TicketEdit.nothing().model_copy(update={"milestone": MilestoneName.fake()})
    assert edit.update(IssueDetail.fake(), viewer()).milestone == Milestone.fake()


def test_a_milestone_is_looked_up_in_the_project_being_moved_to() -> None:
    edit = TicketEdit.nothing().model_copy(
        update={"add_project": ProjectName("Other"), "milestone": MilestoneName.fake()}
    )
    assert edit.update(IssueDetail.fake(), viewer()).milestone == Milestone(
        project=ProjectName("Other"), name=MilestoneName.fake()
    )


def test_a_milestone_without_a_project_is_refused() -> None:
    edit = TicketEdit.nothing().model_copy(update={"milestone": MilestoneName.fake()})
    with pytest.raises(TicketEditError):
        _ = edit.update(held(Issue.fake().model_copy(update={"project": None})), viewer())


def test_removing_the_milestone_clears_it() -> None:
    edit = TicketEdit.nothing().model_copy(update={"remove_milestone": RemoveMilestone(True)})
    assert edit.update(IssueDetail.fake(), viewer()).milestone == Cleared()


def test_setting_and_removing_the_milestone_together_are_refused() -> None:
    edit = TicketEdit.nothing().model_copy(
        update={"milestone": MilestoneName.fake(), "remove_milestone": RemoveMilestone(True)}
    )
    with pytest.raises(TicketEditError):
        _ = edit.checked(FlowLabels.fake())


def test_label_flags_split_on_commas() -> None:
    flags = LabelNames((LabelName("Backend, d-grill"), LabelName("d-implement")))
    assert flags.split() == LabelNames(
        (LabelName("Backend"), LabelName("d-grill"), LabelName("d-implement"))
    )


def test_a_status_is_passed_on() -> None:
    edit = TicketEdit.nothing().model_copy(update={"status": IssueStatusName("Done")})
    assert edit.update(IssueDetail.fake(), viewer()).status == IssueStatusName("Done")


@pytest.mark.parametrize("option", ["add_labels", "remove_labels"])
def test_a_flow_label_in_a_label_option_is_refused(option: str) -> None:
    edit = TicketEdit.nothing().model_copy(update={option: LabelNames((LabelName("specced"),))})
    state_option = "--state"
    with pytest.raises(TicketEditError, match=state_option):
        _ = edit.checked(FlowLabels.fake())
