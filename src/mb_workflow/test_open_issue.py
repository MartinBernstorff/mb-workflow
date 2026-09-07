from mb_workflow.linear import BranchSlug, IssueIdentifier
from mb_workflow.open_issue import worktree_name
from mb_workflow.orca import WorktreeName


def name_of(branch: BranchSlug) -> WorktreeName:
    return worktree_name(branch, IssueIdentifier.fake())


def test_drops_the_git_user_prefix_orca_adds_back() -> None:
    assert name_of(BranchSlug("mab/add-widget")) == WorktreeName("add-widget")


def test_drops_the_issue_identifier_linear_prepends() -> None:
    assert name_of(BranchSlug("mab/e-4289-add-widget")) == WorktreeName("add-widget")


def test_drops_a_slugified_conventional_commit_type() -> None:
    assert name_of(BranchSlug.fake()) == WorktreeName("add-widget")


def test_drops_a_slugified_conventional_commit_scope() -> None:
    assert name_of(BranchSlug("mab/e-4289-fixci-broken-cache")) == WorktreeName("broken-cache")


def test_strips_a_leading_type_like_word_even_when_it_is_not_a_commit_type() -> None:
    assert name_of(BranchSlug("mab/e-4289-feature-flags")) == WorktreeName("flags")


def test_keeps_a_bare_slug_untouched() -> None:
    assert name_of(BranchSlug("mab/add-widget-to-the-thing")) == WorktreeName(
        "add-widget-to-the-thing"
    )


def test_falls_back_to_the_issue_identifier_without_a_branch() -> None:
    assert worktree_name(BranchSlug(""), IssueIdentifier.fake()) == WorktreeName("E-4289")


def test_falls_back_to_a_literal_name_without_a_branch_or_issue() -> None:
    assert worktree_name(BranchSlug(""), None) == WorktreeName("linear-workspace")
