import pytest

from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
from mb_workflow.b_core.d_domain_model.workspace import (
    ProjectSelector,
    UnlinkedWorktreeError,
    Worktree,
)


def test_a_mixed_case_project_selector_is_lowercased() -> None:
    mixed_case = "github:MartinBernstorff/codetaster"
    lowercase = "github:martinbernstorff/codetaster"
    assert ProjectSelector(mixed_case).root == lowercase


def test_a_linked_worktree_yields_its_issue() -> None:
    assert Worktree.fake().linked_issue() == IssueIdentifier.fake()


def test_an_unlinked_worktree_points_to_mw_link() -> None:
    unlinked = Worktree.fake().model_copy(update={"issue": None})
    with pytest.raises(UnlinkedWorktreeError, match="mw link"):
        _ = unlinked.linked_issue()
