from mb_workflow.b_core.a_features.unclaim import TicketUnclaiming
from mb_workflow.b_core.c_secondary_ports.claims import FakeClaimRegistry
from mb_workflow.b_core.d_domain_model.claim import Claim, ClaimId, Claims
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier


def unclaim(claims: FakeClaimRegistry) -> None:
    TicketUnclaiming.unclaim_ticket(registry=claims, ticket=IssueIdentifier.fake()).unwrap()


def test_releases_every_claim_on_the_ticket() -> None:
    later = Claim.fake().model_copy(update={"id": ClaimId("later")})
    claims = FakeClaimRegistry({IssueIdentifier.fake(): Claims((Claim.fake(), later))})
    unclaim(claims)
    assert claims.claims(IssueIdentifier.fake()).unwrap() == Claims(())


def test_leaves_other_tickets_claimed() -> None:
    other = IssueIdentifier("E-1")
    claims = FakeClaimRegistry({IssueIdentifier.fake(): Claims.fake(), other: Claims.fake()})
    unclaim(claims)
    assert claims.claims(other).unwrap() == Claims.fake()


def test_a_ticket_with_no_claim_is_left_alone() -> None:
    claims = FakeClaimRegistry()
    unclaim(claims)
    assert claims.claims(IssueIdentifier.fake()).unwrap() == Claims(())
