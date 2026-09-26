from mb_workflow.b_core.a_features.unclaim import unclaim_ticket
from mb_workflow.b_core.c_secondary_ports.claims import FakeClaimRegistry
from mb_workflow.b_core.d_domain_model.claim import (
    Claim,
    ClaimHolder,
    ClaimId,
    Claims,
    HostName,
)
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier


def rival() -> Claim:
    holder = ClaimHolder.fake().model_copy(update={"host": HostName("bob-mbp.local")})
    return Claim(id=ClaimId("rival"), holder=holder)


def test_releases_a_claim_held_by_another_holder() -> None:
    claims = FakeClaimRegistry({IssueIdentifier.fake(): Claims((rival(),))})
    unclaim_ticket(claims, IssueIdentifier.fake())
    assert claims.claims(IssueIdentifier.fake()) == Claims(())


def test_releases_every_claim_on_the_ticket() -> None:
    claims = FakeClaimRegistry({IssueIdentifier.fake(): Claims((Claim.fake(), rival()))})
    unclaim_ticket(claims, IssueIdentifier.fake())
    assert claims.claims(IssueIdentifier.fake()) == Claims(())


def test_leaves_other_tickets_claimed() -> None:
    other = IssueIdentifier("E-1")
    claims = FakeClaimRegistry(
        {IssueIdentifier.fake(): Claims((rival(),)), other: Claims((Claim.fake(),))}
    )
    unclaim_ticket(claims, IssueIdentifier.fake())
    assert claims.claims(other) == Claims((Claim.fake(),))


def test_unclaiming_an_unclaimed_ticket_succeeds() -> None:
    claims = FakeClaimRegistry()
    unclaim_ticket(claims, IssueIdentifier.fake())
    assert claims.claims(IssueIdentifier.fake()) == Claims(())
