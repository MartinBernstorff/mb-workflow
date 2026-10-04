import logging
from typing import TYPE_CHECKING

from assertions import Assert

from mb_workflow.a_presentation.review_workspaces_report import (
    LoggingNarrator,
    log_review_workspaces_outcome,
)
from mb_workflow.b_core.a_features.review_workspaces import (
    Failure,
    FailureReason,
    FailureSubject,
    Outcome,
)
from mb_workflow.b_core.d_domain_model.pull_request import PrNumber, PullRequests
from mb_workflow.b_core.d_domain_model.workspace import WorktreeName, WorktreePath, Worktrees

if TYPE_CHECKING:
    import pytest


def test_reports_each_created_workspace(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        log_review_workspaces_outcome(Outcome.fake())
    Assert.that(caplog.text).contains("Created 1 workspace:")
    Assert.that(caplog.text).contains(f"    {WorktreeName.fake().root} → ")


def test_reports_each_removed_workspace(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        log_review_workspaces_outcome(
            Outcome(created=(), removed=(WorktreePath.fake(),), failed=())
        )
    Assert.that(caplog.text).contains("Removed 1 workspace:")
    Assert.that(caplog.text).contains(f"    {WorktreePath.fake().root}")


def test_counts_several_workspaces_in_the_plural(caplog: pytest.LogCaptureFixture) -> None:
    removed = (WorktreePath.fake(), WorktreePath.fake().sibling(WorktreeName("pr-7")))
    with caplog.at_level(logging.INFO):
        log_review_workspaces_outcome(Outcome(created=(), removed=removed, failed=()))
    Assert.that(caplog.text).contains("Removed 2 workspaces:")


def test_says_so_when_nothing_changed(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        log_review_workspaces_outcome(Outcome(created=(), removed=(), failed=()))
    Assert.that(caplog.text.strip()).ends_with(
        "Review workspaces already match the PRs awaiting review"
    )


def test_a_run_with_only_failures_reports_no_changes(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        log_review_workspaces_outcome(Outcome(created=(), removed=(), failed=(Failure.fake(),)))
    Assert.that(caplog.text).matches("")


def test_narrates_the_worktrees_it_inspects(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        LoggingNarrator().inspecting(Worktrees.fake(), WorktreePath.fake())
    Assert.that(caplog.text).contains(f"Inspecting 1 worktrees from {WorktreePath.fake().root}")


def test_narrates_the_prs_awaiting_review(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        LoggingNarrator().awaiting_review(PullRequests.fake())
    Assert.that(caplog.text).contains("PRs awaiting your review: 1")


def test_narrates_the_worktree_it_creates_for_a_pr(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        LoggingNarrator().creating(PrNumber.fake())
    Assert.that(caplog.text).contains(f"Creating worktree {WorktreeName.fake().root}")


def test_narrates_a_failed_creation_as_an_error(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        LoggingNarrator().creation_failed(Failure.fake())
    Assert.that([record.levelno for record in caplog.records]).matches([logging.ERROR])
    Assert.that(caplog.text).contains(f"PR #{PrNumber.fake().root} failed: repo_not_found")


def test_narrates_a_failed_removal_as_an_error(caplog: pytest.LogCaptureFixture) -> None:
    failure = Failure(
        subject=FailureSubject.of_path(WorktreePath.fake()), reason=FailureReason.fake()
    )
    with caplog.at_level(logging.INFO):
        LoggingNarrator().removal_failed(failure)
    Assert.that([record.levelno for record in caplog.records]).matches([logging.ERROR])
    Assert.that(caplog.text).contains(
        f"{WorktreePath.fake().root} could not be removed: repo_not_found"
    )
