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


def claimed_label() -> LabelName:
    return LabelName("claimed")


def labelled_tracker() -> FakeTicketTracker:
    issue = Issue.fake().model_copy(
        update={"labels": LabelNames((*Issue.fake().labels.root, claimed_label()))}
    )
    return FakeTicketTracker(
        LabelNames((*LabelNames.fake().root, claimed_label())),
        (TrackedIssue.fake().model_copy(update={"issue": issue}),),
    )


def rival() -> ClaimHolder:
    return ClaimHolder.fake().model_copy(update={"host": HostName("bob-mbp.local")})


def held_by(holder: ClaimHolder) -> FakeClaimRegistry:
    return FakeClaimRegistry(
        {IssueIdentifier.fake(): Claims((Claim(id=ClaimId("held"), holder=holder),))}
    )


def releasing(
    registry: FakeClaimRegistry, tracker: FakeTicketTracker, label: LabelName | None
) -> None:
    release_claim(
        registry,
        tracker,
        ReleaseRequest(ticket=IssueIdentifier.fake(), holder=ClaimHolder.fake(), label=label),
    )


def test_releasing_withdraws_the_holders_claim() -> None:
    registry = held_by(ClaimHolder.fake())
    releasing(registry, labelled_tracker(), claimed_label())
    assert registry.claims(IssueIdentifier.fake()) == Claims(())


def test_with_a_claim_label_configured_releasing_removes_it() -> None:
    tracker = labelled_tracker()
    releasing(held_by(ClaimHolder.fake()), tracker, claimed_label())
    assert tracker.read_issue(IssueIdentifier.fake()).labels == Issue.fake().labels


def test_without_a_claim_label_configured_releasing_leaves_the_labels() -> None:
    tracker = labelled_tracker()
    releasing(held_by(ClaimHolder.fake()), tracker, None)
    assert tracker.read_issue(IssueIdentifier.fake()).labels.has(claimed_label()).root


def test_releasing_leaves_another_holders_claim_and_its_label() -> None:
    registry = held_by(rival())
    tracker = labelled_tracker()
    releasing(registry, tracker, claimed_label())
    assert tuple(claim.holder for claim in registry.claims(IssueIdentifier.fake()).root) == (
        rival(),
    )
    assert tracker.read_issue(IssueIdentifier.fake()).labels.has(claimed_label()).root
