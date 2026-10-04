from safe_result import Err

from mb_workflow.b_core.a_features.teardown import Teardown, TeardownRequest
from mb_workflow.b_core.c_secondary_ports.claims import FakeClaimRegistry
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import FakeTicketTracker, TrackedIssue
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
from mb_workflow.b_core.d_domain_model.config import ClaimSettings
from mb_workflow.b_core.d_domain_model.issue import (
    Issue,
    IssueIdentifier,
    IssueStatusName,
    LabelName,
    LabelNames,
)
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


def tracker_with_the_claimed_label() -> FakeTicketTracker:
    issue = Issue.fake().model_copy(
        update={"labels": LabelNames((*Issue.fake().labels.root, LabelName("claimed")))}
    )
    return FakeTicketTracker(
        LabelNames((*LabelNames.fake().root, LabelName("claimed"))),
        (TrackedIssue.fake().model_copy(update={"issue": issue}),),
    )


def holder_of_ticket(claims: FakeClaimRegistry) -> ClaimHolder | None:
    held = claims.claims(IssueIdentifier.fake()).unwrap().holding(IssueStatusName.fake())
    return None if held is None else held.holder


def managing(*worktrees: Worktree) -> FakeWorkspaceManager:
    here = Worktree.bare(RepoId.fake(), WorktreePath.fake().sibling(WorktreeName("main")))
    return FakeWorkspaceManager(Worktrees((here, *worktrees)), here.path)


def test_releases_the_claim_and_removes_the_worktree() -> None:
    manager = managing(Worktree.fake())
    claims = claimed_by(
        ClaimHolder(host=HostName.fake(), worktree=WorktreeName.of_issue(IssueIdentifier.fake()))
    )
    Teardown.teardown_worktree(
        tracker=tracker_with_the_claimed_label(),
        claim_settings=ClaimSettings.fake(),
        manager=manager,
        claims=claims,
        request=TeardownRequest.fake(),
    ).unwrap()
    assert holder_of_ticket(claims) is None
    assert manager.worktrees().unwrap().at(WorktreePath.fake()) is None


def test_removes_the_claimed_label() -> None:
    tracker = tracker_with_the_claimed_label()
    claims = claimed_by(
        ClaimHolder(host=HostName.fake(), worktree=WorktreeName.of_issue(IssueIdentifier.fake()))
    )
    Teardown.teardown_worktree(
        manager=managing(Worktree.fake()),
        claims=claims,
        tracker=tracker,
        claim_settings=ClaimSettings.fake(),
        request=TeardownRequest.fake(),
    ).unwrap()
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().labels == Issue.fake().labels


def test_withdraws_a_claim_held_from_another_host_and_removes_the_label() -> None:
    elsewhere = ClaimHolder(
        host=HostName("elsewhere.local"), worktree=WorktreeName.of_issue(IssueIdentifier.fake())
    )
    claims = claimed_by(elsewhere)
    tracker = tracker_with_the_claimed_label()
    Teardown.teardown_worktree(
        manager=managing(Worktree.fake()),
        claims=claims,
        tracker=tracker,
        claim_settings=ClaimSettings.fake(),
        request=TeardownRequest.fake(),
    ).unwrap()
    assert holder_of_ticket(claims) is None
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().labels == Issue.fake().labels


def test_tears_down_the_current_worktree_when_none_is_named() -> None:
    current = Worktree.fake()
    manager = FakeWorkspaceManager(Worktrees((current,)), current.path)
    claims = claimed_by(ClaimHolder.fake())
    Teardown.teardown_worktree(
        manager=manager,
        claims=claims,
        tracker=tracker_with_the_claimed_label(),
        claim_settings=ClaimSettings.fake(),
        request=TeardownRequest(worktree=None),
    ).unwrap()
    assert holder_of_ticket(claims) is None
    assert manager.worktrees().unwrap().at(current.path) is None


def test_removes_a_worktree_linked_to_no_ticket() -> None:
    unlinked = Worktree.fake().model_copy(update={"issue": None})
    manager = managing(unlinked)
    Teardown.teardown_worktree(
        tracker=tracker_with_the_claimed_label(),
        claim_settings=ClaimSettings.fake(),
        manager=manager,
        claims=FakeClaimRegistry(),
        request=TeardownRequest.fake(),
    ).unwrap()
    assert manager.worktrees().unwrap().at(WorktreePath.fake()) is None


def test_releases_the_claim_of_a_worktree_orca_suffixed() -> None:
    suffixed = Worktree.fake().model_copy(
        update={"path": WorktreePath.fake().sibling(WorktreeName("E-4289-2"))}
    )
    claims = claimed_by(
        ClaimHolder(host=HostName.fake(), worktree=WorktreeName.of_issue(IssueIdentifier.fake()))
    )
    request = TeardownRequest.fake().model_copy(update={"worktree": WorktreeName("E-4289-2")})
    Teardown.teardown_worktree(
        tracker=tracker_with_the_claimed_label(),
        claim_settings=ClaimSettings.fake(),
        manager=managing(suffixed),
        claims=claims,
        request=request,
    ).unwrap()
    assert holder_of_ticket(claims) is None


def test_refuses_a_worktree_that_does_not_exist() -> None:
    manager = managing()
    request = TeardownRequest.fake().model_copy(update={"worktree": WorktreeName("MB-999")})
    refused = Teardown.teardown_worktree(
        tracker=tracker_with_the_claimed_label(),
        claim_settings=ClaimSettings.fake(),
        manager=manager,
        claims=FakeClaimRegistry(),
        request=request,
    )
    assert refused == Err(WorkspaceManagerError("No worktree is named MB-999."))
    assert manager.worktrees().unwrap() == managing().worktrees().unwrap()
