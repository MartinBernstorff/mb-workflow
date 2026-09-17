import pytest

from mb_workflow.label import UnlinkedWorktreeError, labelled_issue
from mb_workflow.linear import Issue, IssueIdentifier, LabelName, LabelNames
from mb_workflow.orca import Worktree
from mb_workflow.shell import CommandOutput


def test_labels_the_linear_issue_the_worktree_is_linked_to() -> None:
    assert labelled_issue(Worktree.fake()) == IssueIdentifier.fake()


def test_rejects_a_worktree_with_no_linked_linear_issue() -> None:
    worktree = Worktree.fake().model_copy(update={"linked_linear_issue": None})
    with pytest.raises(UnlinkedWorktreeError, match="no linked Linear issue"):
        _ = labelled_issue(worktree)


def test_adding_a_label_keeps_the_labels_already_there() -> None:
    assert LabelName.fake().addition(IssueIdentifier.fake()).root == (
        "linearis",
        "issues",
        "update",
        "E-4289",
        "--labels",
        "d-implement",
        "--label-mode",
        "add",
    )


def test_removing_a_label_overwrites_with_the_ones_left() -> None:
    labels = LabelNames((LabelName("d-grill"), LabelName.fake()))
    assert labels.without(LabelName.fake()).overwrite(IssueIdentifier.fake()).root == (
        "linearis",
        "issues",
        "update",
        "E-4289",
        "--labels",
        "d-grill",
        "--label-mode",
        "overwrite",
    )


def test_removing_the_only_label_clears_them_all() -> None:
    remaining = LabelNames.fake().without(LabelName.fake())
    assert remaining.overwrite(IssueIdentifier.fake()).root == (
        "linearis",
        "issues",
        "update",
        "E-4289",
        "--clear-labels",
    )


def test_removing_a_label_the_issue_does_not_carry_leaves_it_alone() -> None:
    assert LabelNames.fake().without(LabelName("d-grill")) == LabelNames.fake()


def test_reads_the_labels_off_an_issue() -> None:
    output = CommandOutput(
        '{"identifier":"E-4289","state":{"name":"Todo"},'
        '"labels":{"nodes":[{"id":"x","name":"d-implement"}]}}'
    )
    assert Issue.parse(output).label_names() == LabelNames.fake()


def test_an_issue_carries_no_labels_until_told_otherwise() -> None:
    output = CommandOutput('{"identifier":"E-4289","state":{"name":"Todo"}}')
    assert Issue.parse(output).label_names() == LabelNames(())
