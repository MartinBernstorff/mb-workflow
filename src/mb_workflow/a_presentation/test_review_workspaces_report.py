import logging
from typing import TYPE_CHECKING

from mb_workflow.a_presentation.review_workspaces_report import LoggingNarrator, log_outcome
from mb_workflow.b_core.a_features.review_workspaces import Failure, Outcome
from mb_workflow.b_core.d_domain_model.pull_request import PrNumber, PullRequests
from mb_workflow.b_core.d_domain_model.workspace import WorktreeName, WorktreePath, Worktrees

if TYPE_CHECKING:
    import pytest


def test_reports_each_created_workspace(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        log_outcome(Outcome.fake())
    assert "Created 1 workspace:" in caplog.text
    assert f"    {WorktreeName.fake().root} → " in caplog.text


def test_reports_each_removed_workspace(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        log_outcome(Outcome(created=(), removed=(WorktreePath.fake(),), failed=()))
    assert "Removed 1 workspace:" in caplog.text
    assert f"    {WorktreePath.fake().root}" in caplog.text


def test_counts_several_workspaces_in_the_plural(caplog: pytest.LogCaptureFixture) -> None:
    removed = (WorktreePath.fake(), WorktreePath.fake().sibling(WorktreeName("pr-7")))
    with caplog.at_level(logging.INFO):
        log_outcome(Outcome(created=(), removed=removed, failed=()))
    assert "Removed 2 workspaces:" in caplog.text


def test_says_so_when_nothing_changed(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        log_outcome(Outcome(created=(), removed=(), failed=()))
    assert caplog.text.strip().endswith("Review workspaces already match the PRs awaiting review")


def test_a_run_with_only_failures_reports_no_changes(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        log_outcome(Outcome(created=(), removed=(), failed=(Failure.fake(),)))
    assert caplog.text == ""


def test_narrates_the_worktrees_it_inspects(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        LoggingNarrator().inspecting(Worktrees.fake(), WorktreePath.fake())
    assert f"Inspecting 1 worktrees from {WorktreePath.fake().root}" in caplog.text


def test_narrates_the_prs_awaiting_review(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        LoggingNarrator().awaiting_review(PullRequests.fake())
    assert "PRs awaiting your review: 1" in caplog.text


def test_narrates_the_worktree_it_creates_for_a_pr(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        LoggingNarrator().creating(PrNumber.fake())
    assert f"Creating worktree {WorktreeName.fake().root}" in caplog.text


def test_narrates_a_failure_as_an_error(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        LoggingNarrator().failed(Failure.fake())
    assert [record.levelno for record in caplog.records] == [logging.ERROR]
    assert f"PR #{PrNumber.fake().root} failed: repo_not_found" in caplog.text
