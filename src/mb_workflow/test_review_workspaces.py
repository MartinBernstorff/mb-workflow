import logging
from typing import TYPE_CHECKING

from mb_workflow.git import BranchName, Ref
from mb_workflow.github import PrNumber, PrTitle, PullRequest, PullRequests
from mb_workflow.orca import RepoId, Worktree, WorktreeName, WorktreePath, Worktrees
from mb_workflow.review_workspaces import Failure, Outcome, uncovered
from mb_workflow.shell import ExitCode

if TYPE_CHECKING:
    import pytest


def other_pr() -> PullRequest:
    return PullRequest(
        number=PrNumber(7), title=PrTitle("Other work"), head_ref_name=BranchName("feat/other")
    )


def bare_worktree() -> Worktree:
    return Worktree(repo_id=RepoId.fake(), path=WorktreePath.fake())


def test_keeps_prs_with_no_workspace() -> None:
    assert uncovered(PullRequests.fake(), Worktrees((bare_worktree(),))) == PullRequests.fake()


def test_skips_a_pr_linked_by_issue_number() -> None:
    worktrees = Worktrees((bare_worktree().model_copy(update={"linked_issue": PrNumber.fake()}),))
    assert uncovered(PullRequests.fake(), worktrees) == PullRequests(())


def test_skips_a_pr_whose_branch_is_already_checked_out() -> None:
    worktrees = Worktrees((bare_worktree().model_copy(update={"branch": Ref.fake()}),))
    assert uncovered(PullRequests.fake(), worktrees) == PullRequests(())


def test_a_workspace_for_another_pr_does_not_cover_this_one() -> None:
    prs = PullRequests((PullRequest.fake(), other_pr()))
    worktrees = Worktrees((bare_worktree().model_copy(update={"branch": Ref.fake()}),))
    assert uncovered(prs, worktrees) == PullRequests((other_pr(),))


def test_no_prs_yields_nothing_to_do() -> None:
    assert uncovered(PullRequests(()), Worktrees.fake()) == PullRequests(())


def test_a_clean_run_exits_zero() -> None:
    assert Outcome.fake().exit_code() == ExitCode(0)


def test_any_failure_exits_non_zero() -> None:
    assert Outcome(created=(), failed=(Failure.fake(),)).exit_code() == ExitCode(1)


def test_reports_each_created_workspace(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        Outcome.fake().report()
    assert "Created 1 workspace:" in caplog.text
    assert WorktreeName.fake().root in caplog.text


def test_reports_nothing_when_none_were_created(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        Outcome(created=(), failed=()).report()
    assert caplog.text == ""
