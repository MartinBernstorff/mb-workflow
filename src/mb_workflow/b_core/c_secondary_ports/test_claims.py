import pytest

from mb_workflow.b_core.c_secondary_ports.claims import (
    Claiming,
    ClaimRefusedError,
    FakeClaimRegistry,
    LabelledClaim,
)
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import FakeTicketTracker, TrackedIssue
from mb_workflow.b_core.d_domain_model.claim import (
    Claim,
    ClaimHolder,
    ClaimId,
    Claims,
    HostName,
)
from mb_workflow.b_core.d_domain_model.issue import (
    Issue,
    IssueIdentifier,
    LabelName,
    LabelNames,
)


def tracker_with_the_claimed_label() -> FakeTicketTracker:
    issue = Issue.fake().model_copy(
        update={"labels": LabelNames((*Issue.fake().labels.root, LabelName("claimed")))}
    )
    return FakeTicketTracker(
        LabelNames((*LabelNames.fake().root, LabelName("claimed"))),
        (TrackedIssue.fake().model_copy(update={"issue": issue}),),
    )


def rival() -> ClaimHolder:
    return ClaimHolder.fake().model_copy(update={"host": HostName("bob-mbp.local")})


def registry_held_by(*holders: ClaimHolder) -> FakeClaimRegistry:
    return FakeClaimRegistry(
        {
            IssueIdentifier.fake(): Claims(
                tuple(
                    Claim(id=ClaimId(f"held-{index}"), holder=holder)
                    for index, holder in enumerate(holders)
                )
            )
        }
    )


def claim_holders(registry: FakeClaimRegistry) -> tuple[ClaimHolder, ...]:
    return tuple(claim.holder for claim in registry.claims(IssueIdentifier.fake()).root)


def test_releasing_withdraws_the_holders_claim() -> None:
    registry = registry_held_by(ClaimHolder.fake())
    Claiming.release_claim(registry, tracker_with_the_claimed_label(), LabelledClaim.fake())
    assert registry.claims(IssueIdentifier.fake()) == Claims(())


def test_releasing_the_last_claim_removes_the_label() -> None:
    tracker = tracker_with_the_claimed_label()
    labelled = LabelledClaim.fake().model_copy(update={"label": LabelName("claimed")})
    Claiming.release_claim(registry_held_by(ClaimHolder.fake()), tracker, labelled)
    assert tracker.read_issue(IssueIdentifier.fake()).labels == Issue.fake().labels


def test_releasing_leaves_another_holders_claim_and_its_label() -> None:
    registry = registry_held_by(rival())
    tracker = tracker_with_the_claimed_label()
    Claiming.release_claim(registry, tracker, LabelledClaim.fake())
    assert claim_holders(registry) == (rival(),)
    assert tracker.read_issue(IssueIdentifier.fake()).labels.has(LabelName("claimed")).root


def test_releasing_keeps_the_label_while_another_claim_remains() -> None:
    registry = registry_held_by(ClaimHolder.fake(), rival())
    tracker = tracker_with_the_claimed_label()
    Claiming.release_claim(registry, tracker, LabelledClaim.fake())
    assert claim_holders(registry) == (rival(),)
    assert tracker.read_issue(IssueIdentifier.fake()).labels.has(LabelName("claimed")).root


def test_labelling_a_claim_adds_the_label() -> None:
    tracker = FakeTicketTracker(
        LabelNames((*LabelNames.fake().root, LabelName("claimed"))), (TrackedIssue.fake(),)
    )
    Claiming.label_claim_or_withdraw(
        registry_held_by(ClaimHolder.fake()), tracker, LabelledClaim.fake()
    )
    assert tracker.read_issue(IssueIdentifier.fake()).labels.has(LabelName("claimed")).root


def test_a_failed_label_withdraws_only_the_holders_claim() -> None:
    registry = registry_held_by(rival(), ClaimHolder.fake())
    tracker = FakeTicketTracker(LabelNames.fake(), (TrackedIssue.fake(),))
    with pytest.raises(ClaimRefusedError, match="claimed"):
        Claiming.label_claim_or_withdraw(registry, tracker, LabelledClaim.fake())
    assert claim_holders(registry) == (rival(),)
