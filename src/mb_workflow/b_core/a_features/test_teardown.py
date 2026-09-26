import pytest

from mb_workflow.b_core.a_features.teardown import TeardownRequest, teardown_worktree
from mb_workflow.b_core.c_secondary_ports.claims import FakeClaimRegistry
from mb_workflow.b_core.c_secondary_ports.workspace_manager import (
    FakeWorkspaceManager,
    WorkspaceManagerError,
)
from mb_workflow.b_core.d_domain_model.claim import (
    Claim,
    ClaimHolder,
    ClaimId,
    Claims,
    HostName,
)
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier, IssueStatusName
from mb_workflow.b_core.d_domain_model.workspace import (
    RepoId,
    Worktree,
    WorktreeName,
    WorktreePath,
    Worktrees,
)


def claimed_by(*holders: ClaimHolder) -> FakeClaimRegistry:
    return FakeClaimRegistry(
        {
            IssueIdentifier.fake(): Claims(
                tuple(
                    Claim(id=ClaimId(f"claim-{index}"), holder=holder)
                    for index, holder in enumerate(holders)
                )
            )
        }
    )


def holding(claims: FakeClaimRegistry) -> Claim | None:
    return claims.claims(IssueIdentifier.fake()).holding(IssueStatusName("Implementing"))


def managing(*worktrees: Worktree) -> FakeWorkspaceManager:
    here = Worktree.bare(RepoId.fake(), WorktreePath.fake().sibling(WorktreeName("main")))
    return FakeWorkspaceManager(Worktrees((here, *worktrees)), here.path)


def tearing_down(
    manager: FakeWorkspaceManager, claims: FakeClaimRegistry, request: TeardownRequest
) -> None:
    teardown_worktree(manager=manager, claims=claims, request=request)


def test_releases_the_claim_and_removes_the_worktree() -> None:
    manager = managing(Worktree.fake())
    claims = claimed_by(ClaimHolder.fake())
    tearing_down(manager, claims, TeardownRequest.fake())
    assert holding(claims) is None
    assert manager.worktrees().at(WorktreePath.fake()) is None


def test_leaves_a_claim_held_from_another_host() -> None:
    elsewhere = ClaimHolder.fake().model_copy(update={"host": HostName("elsewhere.local")})
    claims = claimed_by(elsewhere)
    tearing_down(managing(Worktree.fake()), claims, TeardownRequest.fake())
    assert holding(claims) == Claim(id=ClaimId("claim-0"), holder=elsewhere)


def test_removes_a_worktree_linked_to_no_ticket() -> None:
    unlinked = Worktree.fake().model_copy(update={"issue": None})
    manager = managing(unlinked)
    tearing_down(manager, FakeClaimRegistry(), TeardownRequest.fake())
    assert manager.worktrees().at(WorktreePath.fake()) is None


def test_refuses_a_worktree_that_does_not_exist() -> None:
    manager = managing()
    request = TeardownRequest.fake().model_copy(update={"worktree": WorktreeName("MB-999")})
    with pytest.raises(WorkspaceManagerError):
        tearing_down(manager, FakeClaimRegistry(), request)
