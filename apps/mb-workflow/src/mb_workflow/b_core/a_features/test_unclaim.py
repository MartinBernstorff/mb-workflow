from mb_workflow.b_core.a_features.unclaim import unclaim_ticket
from mb_workflow.b_core.c_secondary_ports.claims import FakeClaimRegistry
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import FakeTicketTracker, TrackedIssue
from mb_workflow.b_core.d_domain_model.claim import Claim, ClaimId, Claims
from mb_workflow.b_core.d_domain_model.config import ClaimSettings
from mb_workflow.b_core.d_domain_model.issue import Issue, IssueIdentifier, LabelNames


def tracker_with_the_claim_label() -> FakeTicketTracker:
    label = ClaimSettings.fake().label
    issue = Issue.fake().model_copy(
        update={"labels": LabelNames((*Issue.fake().labels.root, label))}
    )
    return FakeTicketTracker(
        LabelNames((*LabelNames.fake().root, label)),
        (TrackedIssue.fake().model_copy(update={"issue": issue}),),
    )


def unclaim(claims: FakeClaimRegistry, tracker: FakeTicketTracker) -> None:
    unclaim_ticket(
        registry=claims,
        tracker=tracker,
        claim_settings=ClaimSettings.fake(),
        ticket=IssueIdentifier.fake(),
    )


def test_releases_every_claim_on_the_ticket() -> None:
    later = Claim.fake().model_copy(update={"id": ClaimId("later")})
    claims = FakeClaimRegistry({IssueIdentifier.fake(): Claims((Claim.fake(), later))})
    unclaim(claims, tracker_with_the_claim_label())
    assert claims.claims(IssueIdentifier.fake()) == Claims(())


def test_leaves_other_tickets_claimed() -> None:
    other = IssueIdentifier("E-1")
    claims = FakeClaimRegistry({IssueIdentifier.fake(): Claims.fake(), other: Claims.fake()})
    unclaim(claims, tracker_with_the_claim_label())
    assert claims.claims(other) == Claims.fake()


def test_removes_the_claim_label() -> None:
    tracker = tracker_with_the_claim_label()
    unclaim(FakeClaimRegistry({IssueIdentifier.fake(): Claims.fake()}), tracker)
    assert tracker.read_issue(IssueIdentifier.fake()).labels == Issue.fake().labels


def test_removes_the_claim_label_from_a_ticket_with_no_claim() -> None:
    tracker = tracker_with_the_claim_label()
    unclaim(FakeClaimRegistry(), tracker)
    assert tracker.read_issue(IssueIdentifier.fake()).labels == Issue.fake().labels
