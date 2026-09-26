from mb_workflow.b_core.a_features.unclaim import unclaim_ticket
from mb_workflow.b_core.c_secondary_ports.claims import FakeClaimRegistry
from mb_workflow.b_core.d_domain_model.claim import Claim, ClaimId, Claims
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier


def test_releases_every_claim_on_the_ticket() -> None:
    later = Claim.fake().model_copy(update={"id": ClaimId("later")})
    claims = FakeClaimRegistry({IssueIdentifier.fake(): Claims((Claim.fake(), later))})
    unclaim_ticket(claims, IssueIdentifier.fake())
    assert claims.claims(IssueIdentifier.fake()) == Claims(())


def test_leaves_other_tickets_claimed() -> None:
    other = IssueIdentifier("E-1")
    claims = FakeClaimRegistry({IssueIdentifier.fake(): Claims.fake(), other: Claims.fake()})
    unclaim_ticket(claims, IssueIdentifier.fake())
    assert claims.claims(other) == Claims.fake()


def test_unclaiming_an_unclaimed_ticket_does_not_raise() -> None:
    unclaim_ticket(FakeClaimRegistry(), IssueIdentifier.fake())
