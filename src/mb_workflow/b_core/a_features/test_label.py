import pytest

from mb_workflow.b_core.a_features.label import (
    LabelChange,
    LabelRequest,
    UnlinkedWorktreeError,
    change_label,
    issue_from_workspace,
    remove_label,
)
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import FakeTicketTracker, TrackedIssue
from mb_workflow.b_core.c_secondary_ports.workspace_manager import FakeWorkspaceManager
from mb_workflow.b_core.d_domain_model.issue import (
    Issue,
    IssueIdentifier,
    LabelName,
    LabelNames,
)
from mb_workflow.b_core.d_domain_model.workspace import Worktree, WorktreePath, Worktrees


def test_labels_the_linear_issue_the_worktree_is_linked_to() -> None:
    assert issue_from_workspace(Worktree.fake()) == IssueIdentifier.fake()


def test_rejects_a_worktree_with_no_linked_linear_issue() -> None:
    worktree = Worktree.fake().model_copy(update={"issue": None})
    with pytest.raises(UnlinkedWorktreeError, match="no linked Linear issue"):
        _ = issue_from_workspace(worktree)


def test_removing_a_label_keeps_the_others() -> None:
    issue = Issue.fake().model_copy(
        update={"labels": LabelNames((LabelName("d-grill"), LabelName.fake()))}
    )
    tracker = FakeTicketTracker(
        LabelNames((LabelName("d-grill"), LabelName.fake())),
        (TrackedIssue.fake().model_copy(update={"issue": issue}),),
    )
    remove_label(tracker, IssueIdentifier.fake(), LabelName.fake())
    assert tracker.read_issue(IssueIdentifier.fake()).labels == LabelNames((LabelName("d-grill"),))


def test_removing_the_only_label_leaves_none() -> None:
    issue = Issue.fake().model_copy(update={"labels": LabelNames.fake()})
    tracker = FakeTicketTracker(
        LabelNames((LabelName("d-grill"), LabelName.fake())),
        (TrackedIssue.fake().model_copy(update={"issue": issue}),),
    )
    remove_label(tracker, IssueIdentifier.fake(), LabelName.fake())
    assert tracker.read_issue(IssueIdentifier.fake()).labels == LabelNames(())


def test_removing_a_label_the_issue_does_not_carry_leaves_it_alone() -> None:
    issue = Issue.fake().model_copy(update={"labels": LabelNames.fake()})
    tracker = FakeTicketTracker(
        LabelNames((LabelName("d-grill"), LabelName.fake())),
        (TrackedIssue.fake().model_copy(update={"issue": issue}),),
    )
    remove_label(tracker, IssueIdentifier.fake(), LabelName("d-grill"))
    assert tracker.read_issue(IssueIdentifier.fake()).labels == LabelNames.fake()


def test_labels_the_issue_linked_to_the_worktree_you_stand_in() -> None:
    issue = Issue.fake().model_copy(update={"labels": LabelNames(())})
    tracker = FakeTicketTracker(
        LabelNames.fake(), (TrackedIssue.fake().model_copy(update={"issue": issue}),)
    )
    manager = FakeWorkspaceManager(Worktrees.fake(), WorktreePath.fake())
    change_label(manager, tracker, LabelRequest.fake())
    assert tracker.read_issue(IssueIdentifier.fake()).labels == LabelNames.fake()


def test_unlabels_the_issue_linked_to_the_worktree_you_stand_in() -> None:
    tracker = FakeTicketTracker(LabelNames.fake(), (TrackedIssue.fake(),))
    manager = FakeWorkspaceManager(Worktrees.fake(), WorktreePath.fake())
    request = LabelRequest(label=LabelName.fake(), change=LabelChange.remove)
    change_label(manager, tracker, request)
    assert tracker.read_issue(IssueIdentifier.fake()).labels == LabelNames(())
