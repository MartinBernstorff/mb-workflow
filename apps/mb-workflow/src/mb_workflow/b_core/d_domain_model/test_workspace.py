import pytest
from assertions import Assert

from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
from mb_workflow.b_core.d_domain_model.workspace import (
    ProjectSelector,
    UnlinkedWorktreeError,
    Worktree,
    WorktreeName,
    WorktreePath,
    Worktrees,
)


def test_a_mixed_case_project_selector_is_lowercased() -> None:
    mixed_case = "github:MartinBernstorff/codetaster"
    lowercase = "github:martinbernstorff/codetaster"
    Assert.that(ProjectSelector(mixed_case).root).matches(lowercase)


def test_a_linked_worktree_yields_its_issue() -> None:
    Assert.that(Worktree.fake().linked_issue()).matches(IssueIdentifier.fake())


def test_an_unlinked_worktree_points_to_mw_link() -> None:
    remedy = "mw link"
    unlinked = Worktree.fake().model_copy(update={"issue": None})
    with pytest.raises(UnlinkedWorktreeError, match=remedy):
        _ = unlinked.linked_issue()


def test_finds_the_worktree_linked_to_an_issue() -> None:
    other = Worktree.fake().model_copy(
        update={"path": WorktreePath.fake().sibling(WorktreeName("other")), "issue": None}
    )
    linked = Worktree.fake()
    Assert.that(Worktrees((other, linked)).linked_to(IssueIdentifier.fake())).matches(linked)


def test_an_issue_typed_in_lowercase_finds_its_worktree() -> None:
    lowercase = IssueIdentifier(IssueIdentifier.fake().root.lower())
    Assert.that(Worktrees.fake().linked_to(lowercase)).matches(Worktree.fake())


def test_an_issue_no_worktree_links_to_finds_none() -> None:
    unlinked_issue = IssueIdentifier("MB-1")
    Assert.that(Worktrees.fake().linked_to(unlinked_issue)).matches(None)
