from typing import TYPE_CHECKING, override

import pytest

from mb_workflow.b_core.a_features.review_workspaces import (
    CreatedWorkspace,
    Failure,
    FailureReason,
    FailureSubject,
    Narrator,
    Outcome,
    Unchanged,
    create_workspaces,
)
from mb_workflow.b_core.c_secondary_ports.claims import FakeClaimRegistry
from mb_workflow.b_core.c_secondary_ports.code_review import FakeCodeReview, MergedPullRequest
from mb_workflow.b_core.c_secondary_ports.run_lock import AlreadyRunningError, FakeRunLock
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import FakeTicketTracker, TrackedIssue
from mb_workflow.b_core.c_secondary_ports.workspace_manager import (
    DisplayNameRefusingWorkspaceManager,
    FakeWorkspaceManager,
)
from mb_workflow.b_core.d_domain_model.claim import Claim, ClaimHolder, Claims, HostName
from mb_workflow.b_core.d_domain_model.config import ClaimSettings
from mb_workflow.b_core.d_domain_model.git import Ref
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier, IssueStatusName, LabelNames
from mb_workflow.b_core.d_domain_model.outcome import Failed
from mb_workflow.b_core.d_domain_model.pull_request import (
    CheckoutDirectory,
    MergedSince,
    PrNumber,
    PrTitle,
    PullRequests,
)
from mb_workflow.b_core.d_domain_model.workspace import (
    DisplayName,
    RepoId,
    WorkspaceStatus,
    Worktree,
    WorktreeName,
    WorktreePath,
    Worktrees,
)

if TYPE_CHECKING:
    from pathlib import Path

    from mb_workflow.b_core.c_secondary_ports.code_review import CodeForge


class SilentNarrator(Narrator):
    @override
    def inspecting(self, worktrees: Worktrees, here: WorktreePath) -> None: ...

    @override
    def awaiting_review(self, prs: PullRequests) -> None: ...

    @override
    def found_obsolete(self, worktrees: Worktrees) -> None: ...

    @override
    def removing(self, path: WorktreePath) -> None: ...

    @override
    def found_uncovered(self, prs: PullRequests) -> None: ...

    @override
    def creating(self, pr: PrNumber) -> None: ...

    @override
    def checking_out(self, path: WorktreePath) -> None: ...

    @override
    def removal_failed(self, failure: Failure) -> None: ...

    @override
    def creation_failed(self, failure: Failure) -> None: ...


@pytest.fixture
def here(tmp_path: Path) -> WorktreePath:
    return WorktreePath(tmp_path / "main")


def standing_in(here: WorktreePath, *others: Worktree) -> FakeWorkspaceManager:
    return FakeWorkspaceManager(Worktrees((Worktree.bare(RepoId.fake(), here), *others)), here)


def create_review_directory(here: WorktreePath) -> WorktreePath:
    path = here.sibling(WorktreeName.fake())
    path.root.mkdir()
    return path


def run_review_workspaces(
    review: CodeForge,
    manager: FakeWorkspaceManager,
    lock: FakeRunLock | None = None,
    status: WorkspaceStatus = WorkspaceStatus.fake(),
    claims: FakeClaimRegistry | None = None,
) -> Outcome:
    return create_workspaces(
        review=review,
        manager=manager,
        claims=FakeClaimRegistry() if claims is None else claims,
        tracker=FakeTicketTracker(LabelNames.fake(), (TrackedIssue.fake(),)),
        claim_settings=ClaimSettings(),
        host=HostName.fake(),
        lock=FakeRunLock() if lock is None else lock,
        narrator=SilentNarrator(),
        status=status,
        since=MergedSince.fake(),
    )


def test_creates_a_workspace_for_a_pr_awaiting_review(here: WorktreePath) -> None:
    path = create_review_directory(here)
    outcome = run_review_workspaces(FakeCodeReview(PullRequests.fake()), standing_in(here))
    assert outcome.created == (CreatedWorkspace(name=WorktreeName.fake(), path=path),)


def test_checks_the_pr_out_into_its_new_workspace(here: WorktreePath) -> None:
    path = create_review_directory(here)
    review = FakeCodeReview(PullRequests.fake())
    _ = run_review_workspaces(review, standing_in(here))
    assert review.checked_out(CheckoutDirectory(path.root)) == PrNumber.fake()


def test_the_new_workspace_sits_in_the_review_status(here: WorktreePath) -> None:
    path = create_review_directory(here)
    manager = standing_in(here)
    _ = run_review_workspaces(FakeCodeReview(PullRequests.fake()), manager)
    created = manager.worktrees().at(path)
    assert created is not None
    assert created.status == WorkspaceStatus.fake()


def test_the_new_workspace_is_named_after_the_pr_title(here: WorktreePath) -> None:
    path = create_review_directory(here)
    manager = standing_in(here)
    _ = run_review_workspaces(FakeCodeReview(PullRequests.fake()), manager)
    created = manager.worktrees().at(path)
    assert created is not None
    assert created.display_name == DisplayName.of_pr(PrTitle.fake())


def test_a_refused_display_name_is_not_a_failed_creation(here: WorktreePath) -> None:
    path = create_review_directory(here)
    manager = DisplayNameRefusingWorkspaceManager(
        Worktrees((Worktree.bare(RepoId.fake(), here),)), here
    )
    outcome = run_review_workspaces(FakeCodeReview(PullRequests.fake()), manager)
    assert outcome.created == (CreatedWorkspace(name=WorktreeName.fake(), path=path),)
    assert outcome.failed == ()


def test_removes_a_review_workspace_whose_pr_no_longer_awaits_review(here: WorktreePath) -> None:
    stale = Worktree.fake().model_copy(update={"path": here.sibling(WorktreeName("stale"))})
    manager = standing_in(here, stale)
    outcome = run_review_workspaces(FakeCodeReview(PullRequests(())), manager)
    assert outcome.removed == (stale.path,)
    assert manager.worktrees().at(stale.path) is None


def test_releases_the_claim_of_a_workspace_it_removes(here: WorktreePath) -> None:
    name = WorktreeName.of_issue(IssueIdentifier.fake())
    stale = Worktree.fake().model_copy(update={"path": here.sibling(name)})
    claims = FakeClaimRegistry(
        {
            IssueIdentifier.fake(): Claims(
                (
                    Claim.fake().model_copy(
                        update={"holder": ClaimHolder.fake().model_copy(update={"worktree": name})}
                    ),
                )
            )
        }
    )
    _ = run_review_workspaces(
        FakeCodeReview(PullRequests(())), standing_in(here, stale), claims=claims
    )
    assert claims.claims(IssueIdentifier.fake()).holding(IssueStatusName.fake()) is None


def test_removes_a_workspace_whose_branch_merged_within_the_lookback(here: WorktreePath) -> None:
    merged = Worktree.bare(RepoId.fake(), here.sibling(WorktreeName("merged"))).model_copy(
        update={"branch": Ref.fake()}
    )
    review = FakeCodeReview(PullRequests(()), merged=(MergedPullRequest.fake(),))
    outcome = run_review_workspaces(review, standing_in(here, merged))
    assert outcome.removed == (merged.path,)


def test_a_workspace_that_already_matches_is_left_unchanged(here: WorktreePath) -> None:
    covered = Worktree.fake().model_copy(update={"path": here.sibling(WorktreeName("covered"))})
    outcome = run_review_workspaces(FakeCodeReview(PullRequests.fake()), standing_in(here, covered))
    assert outcome.unchanged() == Unchanged(True)


def test_a_workspace_that_cannot_be_created_is_reported_as_failed(here: WorktreePath) -> None:
    outcome = run_review_workspaces(
        FakeCodeReview(PullRequests.fake()),
        standing_in(here),
        status=WorkspaceStatus("no-such-column"),
    )
    assert outcome.failed == (
        Failure(
            subject=FailureSubject.of_pr(PrNumber.fake()),
            reason=FailureReason("The board has no column no-such-column."),
        ),
    )
    assert outcome.failed_any() == Failed(True)


def test_a_run_is_refused_while_another_holds_the_lock(here: WorktreePath) -> None:
    lock = FakeRunLock()
    manager = standing_in(here)
    with lock.held(), pytest.raises(AlreadyRunningError):
        _ = run_review_workspaces(FakeCodeReview(PullRequests.fake()), manager, lock)
    assert len(manager.worktrees().root) == 1


def test_a_run_that_touched_nothing_is_unchanged() -> None:
    assert Outcome(created=(), removed=(), failed=()).unchanged() == Unchanged(True)


def test_a_run_that_created_a_workspace_is_not_unchanged() -> None:
    assert Outcome.fake().unchanged() == Unchanged(False)


def test_a_clean_run_exits_zero() -> None:
    assert Outcome.fake().failed_any() == Failed(False)


def test_any_failure_exits_non_zero() -> None:
    assert Outcome(created=(), removed=(), failed=(Failure.fake(),)).failed_any() == Failed(True)
