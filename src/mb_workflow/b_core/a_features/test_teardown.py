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


def holder_of_ticket(claims: FakeClaimRegistry) -> ClaimHolder | None:
    held = claims.claims(IssueIdentifier.fake()).holding(IssueStatusName.fake())
    return None if held is None else held.holder


def managing(*worktrees: Worktree) -> FakeWorkspaceManager:
    here = Worktree.bare(RepoId.fake(), WorktreePath.fake().sibling(WorktreeName("main")))
    return FakeWorkspaceManager(Worktrees((here, *worktrees)), here.path)


def test_releases_the_claim_and_removes_the_worktree() -> None:
    manager = managing(Worktree.fake())
    claims = claimed_by(
        ClaimHolder(host=HostName.fake(), worktree=WorktreeName.of_issue(IssueIdentifier.fake()))
    )
    teardown_worktree(manager=manager, claims=claims, request=TeardownRequest.fake())
    assert holder_of_ticket(claims) is None
    assert manager.worktrees().at(WorktreePath.fake()) is None


def test_leaves_a_claim_held_from_another_host() -> None:
    elsewhere = ClaimHolder(
        host=HostName("elsewhere.local"), worktree=WorktreeName.of_issue(IssueIdentifier.fake())
    )
    claims = claimed_by(elsewhere)
    teardown_worktree(
        manager=managing(Worktree.fake()), claims=claims, request=TeardownRequest.fake()
    )
    assert holder_of_ticket(claims) == elsewhere


def test_removes_a_worktree_linked_to_no_ticket() -> None:
    unlinked = Worktree.fake().model_copy(update={"issue": None})
    manager = managing(unlinked)
    teardown_worktree(manager=manager, claims=FakeClaimRegistry(), request=TeardownRequest.fake())
    assert manager.worktrees().at(WorktreePath.fake()) is None


def test_releases_the_claim_of_a_worktree_orca_suffixed() -> None:
    suffixed = Worktree.fake().model_copy(
        update={"path": WorktreePath.fake().sibling(WorktreeName("E-4289-2"))}
    )
    claims = claimed_by(
        ClaimHolder(host=HostName.fake(), worktree=WorktreeName.of_issue(IssueIdentifier.fake()))
    )
    request = TeardownRequest.fake().model_copy(update={"worktree": WorktreeName("E-4289-2")})
    teardown_worktree(manager=managing(suffixed), claims=claims, request=request)
    assert holder_of_ticket(claims) is None


def test_refuses_a_worktree_that_does_not_exist() -> None:
    manager = managing()
    request = TeardownRequest.fake().model_copy(update={"worktree": WorktreeName("MB-999")})
    with pytest.raises(WorkspaceManagerError):
        teardown_worktree(manager=manager, claims=FakeClaimRegistry(), request=request)
