from typing import TYPE_CHECKING, override

from assertions import Assert
from safe_result import Ok, Result

from mb_workflow.b_core.c_secondary_ports.claims import (
    Claiming,
    ClaimLostError,
    ClaimRequest,
    FakeClaimRegistry,
)
from mb_workflow.b_core.d_domain_model.claim import (
    Claim,
    ClaimHolder,
    ClaimId,
    Claims,
    HostName,
    Posted,
    TakeOver,
)
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTrackerError


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
    return tuple(claim.holder for claim in registry.claims(IssueIdentifier.fake()).unwrap().root)


def test_releasing_withdraws_the_holders_claim() -> None:
    registry = registry_held_by(ClaimHolder.fake())
    Claiming.release_claim(registry, IssueIdentifier.fake(), ClaimHolder.fake()).unwrap()
    Assert.that(registry.claims(IssueIdentifier.fake()).unwrap()).matches(Claims(()))


def test_releasing_leaves_another_holders_claim() -> None:
    registry = registry_held_by(ClaimHolder.fake(), rival())
    Claiming.release_claim(registry, IssueIdentifier.fake(), ClaimHolder.fake()).unwrap()
    Assert.that(claim_holders(registry)).matches((rival(),))


def test_claiming_a_ticket_another_holder_holds_is_refused_as_lost() -> None:
    registry = registry_held_by(rival())
    claimed = Claiming.claim_ticket(registry, ClaimRequest.fake())
    _ = Assert.that(claimed.error).is_instance(ClaimLostError)
    Assert.that(claim_holders(registry)).matches((rival(),))


def test_taking_over_a_claim_replaces_the_other_holders_claim() -> None:
    registry = registry_held_by(rival())
    taking_over = ClaimRequest.fake().model_copy(update={"take_over": TakeOver(True)})
    Assert.that(Claiming.claim_ticket(registry, taking_over)).matches(Ok(Posted(True)))
    Assert.that(claim_holders(registry)).matches((ClaimHolder.fake(),))


# Withdraws every claim as soon as ours is posted, as if another holder took the claim over.
class WithdrawingRegistry(FakeClaimRegistry):
    @override
    def post(
        self, ticket: IssueIdentifier, holder: ClaimHolder
    ) -> Result[ClaimId, TicketTrackerError]:
        posted = super().post(ticket, holder)
        for claim in self.claims(ticket).unwrap().root:
            _ = super().withdraw(ticket, claim.id)
        return posted


def test_a_claim_withdrawn_by_another_is_returned_as_lost() -> None:
    registry = WithdrawingRegistry()
    claimed = Claiming.claim_ticket(registry, ClaimRequest.fake())
    _ = Assert.that(claimed.error).is_instance(ClaimLostError)
    Assert.that(claim_holders(registry)).matches(())
