import logging
from itertools import count
from typing import TYPE_CHECKING, Protocol, override

from safe_result import Err, Ok, Result

from mb_workflow.b_core.d_domain_model.claim import (
    Claim,
    ClaimHolder,
    ClaimId,
    Claims,
    Posted,
    TakeOver,
)
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier, IssueStatusName
from mb_workflow.d_lib.logging import Activity
from mb_workflow.d_lib.models import Model

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTrackerError

logger = logging.getLogger(__name__)


class ClaimRefusedError(Exception):
    pass


# Split out so a drain can move on when another host wins, yet stop on any other refusal.
class ClaimLostError(ClaimRefusedError):
    pass


class ClaimRegistry(Protocol):
    def claims(self, ticket: IssueIdentifier) -> Result[Claims, TicketTrackerError]: ...

    def post(
        self, ticket: IssueIdentifier, holder: ClaimHolder
    ) -> Result[ClaimId, TicketTrackerError]: ...

    def withdraw(
        self, ticket: IssueIdentifier, claim: ClaimId
    ) -> Result[None, TicketTrackerError]: ...


class ClaimRequest(Model):
    ticket: IssueIdentifier
    status: IssueStatusName
    holder: ClaimHolder
    take_over: TakeOver

    @staticmethod
    def fake() -> ClaimRequest:
        return ClaimRequest(
            ticket=IssueIdentifier.fake(),
            status=IssueStatusName("Specced"),
            holder=ClaimHolder.fake(),
            take_over=TakeOver.fake(),
        )


class Claiming:
    @staticmethod
    def claim_ticket(
        registry: ClaimRegistry, request: ClaimRequest
    ) -> Result[Posted, TicketTrackerError | ClaimLostError]:
        with Activity(f"Reading the claims on {request.ticket.root}").logged(logger):
            held = registry.claims(request.ticket)
        if isinstance(held, Err):
            return held
        current = held.value.holding(request.status)
        if current is not None and current.holder == request.holder:
            return Ok(Posted(False))
        if current is not None and not request.take_over.root:
            return Err(Claiming.claimed_error(request.ticket, current))
        withdrawn = Claiming.withdraw_claims(registry, request.ticket, held.value)
        if isinstance(withdrawn, Err):
            return withdrawn
        return Claiming.post_claim(registry, request)

    @staticmethod
    def post_claim(
        registry: ClaimRegistry, request: ClaimRequest
    ) -> Result[Posted, TicketTrackerError | ClaimLostError]:
        # Every claimer posts before reading, so each reads back the same earliest claim, provided Linear serves a just-posted comment at once.
        with Activity(f"Posting a claim on {request.ticket.root}").logged(logger):
            posted = registry.post(request.ticket, request.holder)
        if isinstance(posted, Err):
            return posted
        with Activity(f"Reading back the claims on {request.ticket.root}").logged(logger):
            read_back = registry.claims(request.ticket)
        if isinstance(read_back, Err):
            return read_back
        winner = read_back.value.holding(request.status)
        if winner is not None and winner.id == posted.value:
            return Ok(Posted(True))
        if posted.value in read_back.value.ids():
            with Activity(f"Withdrawing our claim on {request.ticket.root}").logged(logger):
                ours = registry.withdraw(request.ticket, posted.value)
            if isinstance(ours, Err):
                return ours
        if winner is None:
            return Err(
                ClaimLostError(f"Our claim on {request.ticket.root} was withdrawn by another.")
            )
        return Err(Claiming.claimed_error(request.ticket, winner))

    @staticmethod
    def withdraw_claims(
        registry: ClaimRegistry, ticket: IssueIdentifier, held: Claims
    ) -> Result[None, TicketTrackerError]:
        for claim in held.root:
            with Activity(
                f"Withdrawing the claim of worktree {claim.holder.worktree.root}"
                f" on {claim.holder.host.root}"
            ).logged(logger):
                withdrawn = registry.withdraw(ticket, claim.id)
            if isinstance(withdrawn, Err):
                return withdrawn
        return Ok(None)

    @staticmethod
    def claimed_error(ticket: IssueIdentifier, holder: Claim) -> ClaimLostError:
        return ClaimLostError(
            f"{ticket.root} is claimed by worktree {holder.holder.worktree.root}"
            f" on {holder.holder.host.root}. Pass --force to take the claim over."
        )

    @staticmethod
    def withdraw_holders_claims(
        registry: ClaimRegistry, ticket: IssueIdentifier, holder: ClaimHolder
    ) -> Result[None, TicketTrackerError]:
        match registry.claims(ticket):
            case Ok(held):
                for claim in held.root:
                    if claim.holder == holder:
                        withdrawn = registry.withdraw(ticket, claim.id)
                        if isinstance(withdrawn, Err):
                            return withdrawn
                return Ok(None)
            case Err() as failed:
                return failed

    @staticmethod
    def release_claim(
        registry: ClaimRegistry, ticket: IssueIdentifier, holder: ClaimHolder
    ) -> Result[None, TicketTrackerError]:
        with Activity(f"Releasing the claim on {ticket.root}").logged(logger):
            return Claiming.withdraw_holders_claims(registry, ticket, holder)


class FakeClaimRegistry(ClaimRegistry):
    def __init__(self, claims: dict[IssueIdentifier, Claims] | None = None) -> None:
        self._claims = dict(claims or {})
        self._ids = count(1)

    @override
    def claims(self, ticket: IssueIdentifier) -> Result[Claims, TicketTrackerError]:
        return Ok(self._held_claims(ticket))

    @override
    def post(
        self, ticket: IssueIdentifier, holder: ClaimHolder
    ) -> Result[ClaimId, TicketTrackerError]:
        posted = Claim(id=ClaimId(f"claim-{next(self._ids)}"), holder=holder)
        self._claims[ticket] = Claims((*self._held_claims(ticket).root, posted))
        return Ok(posted.id)

    @override
    def withdraw(self, ticket: IssueIdentifier, claim: ClaimId) -> Result[None, TicketTrackerError]:
        self._claims[ticket] = Claims(
            tuple(held for held in self._held_claims(ticket).root if held.id != claim)
        )
        return Ok(None)

    def _held_claims(self, ticket: IssueIdentifier) -> Claims:
        return self._claims.get(ticket, Claims(()))
