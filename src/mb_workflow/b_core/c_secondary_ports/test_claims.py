from mb_workflow.b_core.c_secondary_ports.claims import (
    FakeClaimRegistry,
    ReleaseRequest,
    release_claim,
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
    release_claim(registry, tracker_with_the_claimed_label(), ReleaseRequest.fake())
    assert registry.claims(IssueIdentifier.fake()) == Claims(())


def test_with_a_claim_label_configured_releasing_removes_it() -> None:
    tracker = tracker_with_the_claimed_label()
    labelled = ReleaseRequest.fake().model_copy(update={"label": LabelName("claimed")})
    release_claim(registry_held_by(ClaimHolder.fake()), tracker, labelled)
    assert tracker.read_issue(IssueIdentifier.fake()).labels == Issue.fake().labels


def test_without_a_claim_label_configured_releasing_leaves_the_labels() -> None:
    tracker = tracker_with_the_claimed_label()
    unlabelled = ReleaseRequest.fake().model_copy(update={"label": None})
    release_claim(registry_held_by(ClaimHolder.fake()), tracker, unlabelled)
    assert tracker.read_issue(IssueIdentifier.fake()).labels.has(LabelName("claimed")).root


def test_releasing_leaves_another_holders_claim_and_its_label() -> None:
    registry = registry_held_by(rival())
    tracker = tracker_with_the_claimed_label()
    release_claim(registry, tracker, ReleaseRequest.fake())
    assert claim_holders(registry) == (rival(),)
    assert tracker.read_issue(IssueIdentifier.fake()).labels.has(LabelName("claimed")).root


def test_releasing_keeps_the_label_while_another_claim_remains() -> None:
    registry = registry_held_by(ClaimHolder.fake(), rival())
    tracker = tracker_with_the_claimed_label()
    release_claim(registry, tracker, ReleaseRequest.fake())
    assert claim_holders(registry) == (rival(),)
    assert tracker.read_issue(IssueIdentifier.fake()).labels.has(LabelName("claimed")).root
