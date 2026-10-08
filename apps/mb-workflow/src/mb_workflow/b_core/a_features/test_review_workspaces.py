from typing import TYPE_CHECKING, override

import pytest
from safe_result import Err

from mb_workflow.b_core.a_features.review_workspaces import (
    CreatedWorkspace,
    Failure,
    FailureReason,
    FailureSubject,
    Narrator,
    Outcome,
    ReviewPrompt,
    ReviewWorkspaces,
    Unchanged,
)
from mb_workflow.b_core.c_secondary_ports.claims import FakeClaimRegistry
from mb_workflow.b_core.c_secondary_ports.code_review import (
    CodeReviewError,
    FakeCodeReview,
    MergedPullRequest,
    UnreachableCodeReview,
)
from mb_workflow.b_core.c_secondary_ports.run_lock import AlreadyRunningError, FakeRunLock
from mb_workflow.b_core.c_secondary_ports.status import FakeStatusStore, UnreachableStatusStore
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import FakeTicketTracker, TrackedIssue
from mb_workflow.b_core.c_secondary_ports.workspace_manager import (
    DisplayNameRefusingWorkspaceManager,
    FakeWorkspaceManager,
    WorkspaceManagerError,
)
from mb_workflow.b_core.d_domain_model.claim import Claim, ClaimHolder, Claims, HostName
from mb_workflow.b_core.d_domain_model.config import ClaimSettings
from mb_workflow.b_core.d_domain_model.flow import ReviewChart, StateName, StateNames
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
    WorkspaceStatuses,
    Worktree,
    WorktreeName,
    WorktreePath,
    Worktrees,
)

if TYPE_CHECKING:
    from pathlib import Path

    from safe_result import Result

    from mb_workflow.b_core.c_secondary_ports.code_review import CodeForge
    from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore


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


def fake_board() -> FakeStatusStore:
    return FakeStatusStore(StateName.fake())


def column_of(state: StateName) -> WorkspaceStatus:
    return fake_board().status_for(state).unwrap()


# The fake board names a column for every state, so the manager must hold every review column.
def review_columns() -> WorkspaceStatuses:
    return WorkspaceStatuses(
        tuple(column_of(state) for state in StateNames.of_chart(ReviewChart).root)
    )


def standing_in(
    here: WorktreePath, *others: Worktree, columns: WorkspaceStatuses | None = None
) -> FakeWorkspaceManager:
    return FakeWorkspaceManager(
        Worktrees((Worktree.bare(RepoId.fake(), here), *others)),
        here,
        review_columns() if columns is None else columns,
    )


def in_review(here: WorktreePath, state: StateName = StateName("agent-reviewing")) -> Worktree:
    return Worktree.fake().model_copy(
        update={"path": here.sibling(WorktreeName("stale")), "status": column_of(state)}
    )


def create_review_directory(here: WorktreePath) -> WorktreePath:
    path = here.sibling(WorktreeName.fake())
    path.root.mkdir()
    return path


def run_review_workspaces(
    review: CodeForge,
    manager: FakeWorkspaceManager,
    *,
    claims: FakeClaimRegistry | None = None,
    prompt: ReviewPrompt | None = None,
) -> Outcome:
    return ReviewWorkspacesRuns.attempted(review, manager, claims=claims, prompt=prompt).unwrap()


class ReviewWorkspacesRuns:
    @staticmethod
    def attempted(
        review: CodeForge,
        manager: FakeWorkspaceManager,
        lock: FakeRunLock | None = None,
        *,
        board: WorkspaceStatusStore | None = None,
        claims: FakeClaimRegistry | None = None,
        prompt: ReviewPrompt | None = None,
    ) -> Result[Outcome, AlreadyRunningError | CodeReviewError | WorkspaceManagerError]:
        return ReviewWorkspaces.create_workspaces(
            review=review,
            manager=manager,
            claims=FakeClaimRegistry() if claims is None else claims,
            tracker=FakeTicketTracker(LabelNames.fake(), (TrackedIssue.fake(),)),
            claim_settings=ClaimSettings(),
            host=HostName.fake(),
            lock=FakeRunLock() if lock is None else lock,
            narrator=SilentNarrator(),
            board=fake_board() if board is None else board,
            since=MergedSince.fake(),
            prompt=prompt,
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


def test_the_new_workspace_starts_in_agent_review(here: WorktreePath) -> None:
    path = create_review_directory(here)
    manager = standing_in(here)
    agent_reviewing = column_of(StateName("agent-reviewing"))
    _ = run_review_workspaces(FakeCodeReview(PullRequests.fake()), manager)
    created = manager.worktrees().unwrap().at(path)
    assert created is not None
    assert created.status == agent_reviewing


def test_the_new_workspace_is_named_after_the_pr_title(here: WorktreePath) -> None:
    path = create_review_directory(here)
    manager = standing_in(here)
    _ = run_review_workspaces(FakeCodeReview(PullRequests.fake()), manager)
    created = manager.worktrees().unwrap().at(path)
    assert created is not None
    assert created.display_name == DisplayName.of_pr(PrTitle.fake())


def test_the_prompt_is_submitted_in_the_new_workspace(here: WorktreePath) -> None:
    _ = create_review_directory(here)
    manager = standing_in(here)
    _ = run_review_workspaces(
        FakeCodeReview(PullRequests.fake()), manager, prompt=ReviewPrompt.fake()
    )
    assert manager.submitted_texts() == (ReviewPrompt.fake().text,)


def test_without_a_prompt_nothing_is_typed(here: WorktreePath) -> None:
    _ = create_review_directory(here)
    manager = standing_in(here)
    _ = run_review_workspaces(FakeCodeReview(PullRequests.fake()), manager)
    assert manager.typed_texts() == ()


def test_a_refused_display_name_is_not_a_failed_creation(here: WorktreePath) -> None:
    path = create_review_directory(here)
    manager = DisplayNameRefusingWorkspaceManager(
        Worktrees((Worktree.bare(RepoId.fake(), here),)), here, review_columns()
    )
    outcome = run_review_workspaces(FakeCodeReview(PullRequests.fake()), manager)
    assert outcome.created == (CreatedWorkspace(name=WorktreeName.fake(), path=path),)
    assert outcome.failed == ()


@pytest.mark.parametrize("state", [StateName("agent-reviewing"), StateName("reviewing")])
def test_removes_a_review_workspace_whose_pr_no_longer_awaits_review(
    here: WorktreePath, state: StateName
) -> None:
    stale = in_review(here, state)
    manager = standing_in(here, stale)
    outcome = run_review_workspaces(FakeCodeReview(PullRequests(())), manager)
    assert outcome.removed == (stale.path,)
    assert manager.worktrees().unwrap().at(stale.path) is None


def test_keeps_a_workspace_outside_the_review_columns(here: WorktreePath) -> None:
    implementing = WorkspaceStatus("status-implementing")
    elsewhere = in_review(here).model_copy(update={"status": implementing})
    manager = standing_in(
        here, elsewhere, columns=WorkspaceStatuses((*review_columns().root, implementing))
    )
    outcome = run_review_workspaces(FakeCodeReview(PullRequests(())), manager)
    assert outcome.removed == ()
    assert manager.worktrees().unwrap().at(elsewhere.path) == elsewhere


def test_releases_the_claim_of_a_workspace_it_removes(here: WorktreePath) -> None:
    name = WorktreeName.of_issue(IssueIdentifier.fake())
    stale = in_review(here).model_copy(update={"path": here.sibling(name)})
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
    assert claims.claims(IssueIdentifier.fake()).unwrap().holding(IssueStatusName.fake()) is None


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
    agent_reviewing = column_of(StateName("agent-reviewing"))
    without_agent_review = WorkspaceStatuses(
        tuple(column for column in review_columns().root if column != agent_reviewing)
    )
    outcome = run_review_workspaces(
        FakeCodeReview(PullRequests.fake()), standing_in(here, columns=without_agent_review)
    )
    assert outcome.failed == (
        Failure(
            subject=FailureSubject.of_pr(PrNumber.fake()),
            reason=FailureReason(f"The board has no column {agent_reviewing.root}."),
        ),
    )
    assert outcome.failed_any() == Failed(True)


def test_an_unreachable_board_fails_the_run_and_leaves_workspaces_alone(
    here: WorktreePath,
) -> None:
    _ = create_review_directory(here)
    manager = standing_in(here, in_review(here))
    before = manager.worktrees().unwrap()
    reconciled = ReviewWorkspacesRuns.attempted(
        FakeCodeReview(PullRequests.fake()),
        manager,
        board=UnreachableStatusStore(),
    )
    assert isinstance(reconciled, Err)
    assert isinstance(reconciled.error, WorkspaceManagerError)
    assert manager.worktrees().unwrap() == before


def test_a_checkout_that_is_refused_is_reported_as_failed(here: WorktreePath) -> None:
    # No review directory is created, so the code review refuses to check out into it.
    outcome = run_review_workspaces(FakeCodeReview(PullRequests.fake()), standing_in(here))
    assert [failure.subject for failure in outcome.failed] == [
        FailureSubject.of_pr(PrNumber.fake())
    ]
    assert outcome.created == ()


def test_an_unreachable_code_review_fails_the_run_and_leaves_workspaces_alone(
    here: WorktreePath,
) -> None:
    manager = standing_in(here, in_review(here))
    before = manager.worktrees().unwrap()
    reconciled = ReviewWorkspacesRuns.attempted(UnreachableCodeReview(), manager)
    assert isinstance(reconciled, Err)
    assert isinstance(reconciled.error, CodeReviewError)
    assert manager.worktrees().unwrap() == before


def test_an_unlisted_current_worktree_fails_the_run_and_creates_nothing(
    here: WorktreePath,
) -> None:
    _ = create_review_directory(here)
    review = FakeCodeReview(PullRequests.fake())
    manager = FakeWorkspaceManager(Worktrees(()), here)
    reconciled = ReviewWorkspacesRuns.attempted(review, manager)
    assert reconciled == Err(WorkspaceManagerError(f"No worktree is at {here.root}."))
    assert manager.worktrees().unwrap() == Worktrees(())


def test_a_run_is_refused_while_another_holds_the_lock(here: WorktreePath) -> None:
    lock = FakeRunLock()
    manager = standing_in(here)
    with lock.acquire().unwrap():
        refused = ReviewWorkspacesRuns.attempted(FakeCodeReview(PullRequests.fake()), manager, lock)
    assert isinstance(refused.error, AlreadyRunningError)
    assert len(manager.worktrees().unwrap().root) == 1


def test_a_run_that_touched_nothing_is_unchanged() -> None:
    assert Outcome(created=(), removed=(), failed=()).unchanged() == Unchanged(True)


def test_a_run_that_created_a_workspace_is_not_unchanged() -> None:
    assert Outcome.fake().unchanged() == Unchanged(False)


def test_a_clean_run_exits_zero() -> None:
    assert Outcome.fake().failed_any() == Failed(False)


def test_any_failure_exits_non_zero() -> None:
    assert Outcome(created=(), removed=(), failed=(Failure.fake(),)).failed_any() == Failed(True)
