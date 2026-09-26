from typing import TYPE_CHECKING

import pytest

from mb_workflow.b_core.a_features.edit_issue import (
    BodyFile,
    EditRequest,
    InvalidEditError,
    RemoveMilestone,
    UnlinkedWorktreeError,
    edit_issue,
    issue_from_workspace,
)
from mb_workflow.b_core.c_secondary_ports.issue_tracker import FakeIssueTracker, TrackedIssue
from mb_workflow.b_core.d_domain_model.issue import (
    Assignee,
    Clear,
    Issue,
    IssueBody,
    IssueIdentifier,
    IssueReference,
    IssueTitle,
    LabelName,
    LabelNames,
    MilestoneName,
    ProjectName,
    UnreadableReferenceError,
)
from mb_workflow.c_infrastructure.orca import Orca, Workspace
from mb_workflow.c_infrastructure.shell import ExistingDirectory, Shell

if TYPE_CHECKING:
    from pathlib import Path


def tracking(issue: Issue) -> FakeIssueTracker:
    return FakeIssueTracker(
        LabelNames((LabelName("d-grill"), LabelName.fake())),
        (TrackedIssue.fake().model_copy(update={"issue": issue}),),
    )


def unused_orca(directory: ExistingDirectory) -> Orca:
    return Orca(Shell(directory))


def test_an_identifier_is_its_own_reference() -> None:
    assert IssueReference("E-4289").identifier() == IssueIdentifier.fake()


def test_a_url_references_the_issue_it_links_to() -> None:
    assert IssueReference.fake().identifier() == IssueIdentifier.fake()


def test_a_lowercase_identifier_is_read_as_uppercase() -> None:
    assert IssueReference("e-4289").identifier() == IssueIdentifier.fake()


def test_a_reference_to_no_issue_is_refused() -> None:
    with pytest.raises(UnreadableReferenceError):
        _ = IssueReference("https://linear.app/flowbase/project/widgets").identifier()


def test_comma_separated_labels_are_split() -> None:
    flags = LabelNames((LabelName("d-grill, Backend"), LabelName.fake()))
    assert flags.split() == LabelNames(
        (LabelName("d-grill"), LabelName("Backend"), LabelName.fake())
    )


def test_an_edit_that_changes_nothing_is_refused() -> None:
    with pytest.raises(InvalidEditError, match="at least one"):
        _ = EditRequest.unchanged(None).edit(Issue.fake(), tracking(Issue.fake()))


def test_a_body_and_a_body_file_together_are_refused() -> None:
    request = EditRequest.fake().model_copy(
        update={"body": IssueBody.fake(), "body_file": BodyFile.fake()}
    )
    with pytest.raises(InvalidEditError, match="--body-file"):
        _ = request.edit(Issue.fake(), tracking(Issue.fake()))


def test_setting_and_removing_a_milestone_together_is_refused() -> None:
    request = EditRequest.fake().model_copy(
        update={"milestone": MilestoneName.fake(), "remove_milestone": RemoveMilestone(True)}
    )
    with pytest.raises(InvalidEditError, match="--remove-milestone"):
        _ = request.edit(Issue.fake(), tracking(Issue.fake()))


def test_the_body_is_read_from_the_body_file(tmp_path: Path) -> None:
    _ = (tmp_path / "body.md").write_text(IssueBody.fake().root)
    request = EditRequest.unchanged(None).model_copy(
        update={"body_file": BodyFile(tmp_path / "body.md")}
    )
    assert request.edit(Issue.fake(), tracking(Issue.fake())).body == IssueBody.fake()


def test_me_is_assigned_as_the_viewer() -> None:
    request = EditRequest.unchanged(None).model_copy(update={"add_assignee": Assignee.me()})
    tracker = tracking(Issue.fake())
    assert request.edit(Issue.fake(), tracker).assignee == tracker.viewer()


def test_removing_the_current_assignee_clears_it() -> None:
    issue = Issue.fake().model_copy(update={"assignee": Assignee.fake()})
    request = EditRequest.unchanged(None).model_copy(update={"remove_assignee": Assignee.me()})
    assert request.edit(issue, tracking(issue)).assignee == Clear()


def test_removing_someone_else_leaves_the_assignee() -> None:
    issue = Issue.fake().model_copy(update={"assignee": Assignee.fake()})
    request = EditRequest.unchanged(None).model_copy(
        update={"remove_assignee": Assignee("someone@flowbase.io")}
    )
    assert request.edit(issue, tracking(issue)).assignee is None


def test_adding_an_assignee_wins_over_removing_one() -> None:
    issue = Issue.fake().model_copy(update={"assignee": Assignee.fake()})
    request = EditRequest.unchanged(None).model_copy(
        update={"add_assignee": Assignee("someone@flowbase.io"), "remove_assignee": Assignee.me()}
    )
    assert request.edit(issue, tracking(issue)).assignee == Assignee("someone@flowbase.io")


def test_removing_the_current_project_whatever_its_case_clears_it() -> None:
    request = EditRequest.unchanged(None).model_copy(
        update={"remove_project": ProjectName(ProjectName.fake().root.upper())}
    )
    assert request.edit(Issue.fake(), tracking(Issue.fake())).project == Clear()


def test_removing_another_project_leaves_the_current_one() -> None:
    request = EditRequest.unchanged(None).model_copy(
        update={"remove_project": ProjectName("BE Shop")}
    )
    assert request.edit(Issue.fake(), tracking(Issue.fake())).project is None


def test_removing_the_milestone_clears_it() -> None:
    request = EditRequest.unchanged(None).model_copy(
        update={"remove_milestone": RemoveMilestone(True)}
    )
    assert request.edit(Issue.fake(), tracking(Issue.fake())).milestone == Clear()


def test_an_edit_reaches_the_referenced_issue(tmp_path: Path) -> None:
    tracker = tracking(Issue.fake())
    request = EditRequest.fake().model_copy(
        update={
            "target": IssueReference.fake(),
            "add_labels": LabelNames((LabelName("d-grill"),)),
            "remove_labels": LabelNames((LabelName.fake(),)),
        }
    )
    url = edit_issue(unused_orca(ExistingDirectory(tmp_path)), tracker, request)
    issue = tracker.read_issue(IssueIdentifier.fake())
    assert IssueIdentifier.fake().root in url.root
    assert (issue.title, issue.labels) == (IssueTitle.fake(), LabelNames((LabelName("d-grill"),)))


def test_labelling_adds_one_label(tmp_path: Path) -> None:
    tracker = tracking(Issue.fake())
    request = EditRequest.labelling(LabelName("d-grill")).model_copy(
        update={"target": IssueReference.fake()}
    )
    _ = edit_issue(unused_orca(ExistingDirectory(tmp_path)), tracker, request)
    assert tracker.read_issue(IssueIdentifier.fake()).labels == LabelNames(
        (LabelName.fake(), LabelName("d-grill"))
    )


def test_unlabelling_the_only_label_leaves_none(tmp_path: Path) -> None:
    tracker = tracking(Issue.fake())
    request = EditRequest.unlabelling(LabelName.fake()).model_copy(
        update={"target": IssueReference.fake()}
    )
    _ = edit_issue(unused_orca(ExistingDirectory(tmp_path)), tracker, request)
    assert tracker.read_issue(IssueIdentifier.fake()).labels == LabelNames(())


def test_edits_the_issue_the_worktree_is_linked_to() -> None:
    assert issue_from_workspace(Workspace.fake()) == IssueIdentifier.fake()


def test_rejects_a_worktree_with_no_linked_linear_issue() -> None:
    worktree = Workspace.fake().model_copy(update={"linked_linear_issue": None})
    with pytest.raises(UnlinkedWorktreeError, match="no linked Linear issue"):
        _ = issue_from_workspace(worktree)
