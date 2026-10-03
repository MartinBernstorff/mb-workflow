import logging
from itertools import count
from typing import Protocol, override

from safe_result import Err, Ok, Result

from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
    LabelCheck,
    TicketTracker,
    TicketTrackerError,
)
from mb_workflow.b_core.d_domain_model.claim import (
    Claim,
    ClaimHolder,
    ClaimId,
    Claims,
    Posted,
    TakeOver,
)
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier, IssueStatusName, LabelName
from mb_workflow.d_lib.logging import Activity
from mb_workflow.d_lib.models import Model

logger = logging.getLogger(__name__)


class ClaimRefusedError(Exception):
    pass


# Split out so a drain can move on when another host wins, yet stop on any other refusal.
class ClaimLostError(ClaimRefusedError):
    pass


# The configured claim label does not exist, so no claim can succeed until the config changes.
class UnknownClaimLabelError(ClaimRefusedError):
    pass


class ClaimRegistry(Protocol):
    def claims(self, ticket: IssueIdentifier) -> Result[Claims, TicketTrackerError]: ...

    def post(self, ticket: IssueIdentifier, holder: ClaimHolder) -> ClaimId: ...

    def withdraw(self, ticket: IssueIdentifier, claim: ClaimId) -> None: ...


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
    ) -> Result[Posted, TicketTrackerError]:
        with Activity(f"Reading the claims on {request.ticket.root}").logged(logger):
            held = registry.claims(request.ticket)
        if isinstance(held, Err):
            return held
        current = held.value.holding(request.status)
        if current is not None and current.holder == request.holder:
            return Ok(Posted(False))
        if current is not None and not request.take_over.root:
            raise Claiming.claimed_error(request.ticket, current)
        Claiming.withdraw_claims(registry, request.ticket, held.value)

        # Every claimer posts before reading, so each reads back the same earliest claim, provided Linear serves a just-posted comment at once.
        with Activity(f"Posting a claim on {request.ticket.root}").logged(logger):
            posted = registry.post(request.ticket, request.holder)
        with Activity(f"Reading back the claims on {request.ticket.root}").logged(logger):
            read_back = registry.claims(request.ticket)
        if isinstance(read_back, Err):
            return read_back
        winner = read_back.value.holding(request.status)
        if winner is not None and winner.id == posted:
            return Ok(Posted(True))
        if posted in read_back.value.ids():
            with Activity(f"Withdrawing our claim on {request.ticket.root}").logged(logger):
                registry.withdraw(request.ticket, posted)
        if winner is None:
            raise ClaimLostError(f"Our claim on {request.ticket.root} was withdrawn by another.")
        raise Claiming.claimed_error(request.ticket, winner)

    @staticmethod
    def withdraw_claims(registry: ClaimRegistry, ticket: IssueIdentifier, held: Claims) -> None:
        for claim in held.root:
            with Activity(
                f"Withdrawing the claim of worktree {claim.holder.worktree.root}"
                f" on {claim.holder.host.root}"
            ).logged(logger):
                registry.withdraw(ticket, claim.id)

    @staticmethod
    def claimed_error(ticket: IssueIdentifier, holder: Claim) -> ClaimLostError:
        return ClaimLostError(
            f"{ticket.root} is claimed by worktree {holder.holder.worktree.root}"
            f" on {holder.holder.host.root}. Pass --force to take the claim over."
        )

    # Checked before claiming, so a doomed claim never withdraws another holder's claim.
    @staticmethod
    def require_claim_label(
        tracker: TicketTracker, label: LabelName
    ) -> Result[None, TicketTrackerError]:
        return LabelCheck.require_label(
            tracker,
            label,
            UnknownClaimLabelError(
                f"No label is named {label.root}. Create the label or change claims.label."
            ),
        )

    @staticmethod
    def label_claim(
        tracker: TicketTracker, request: LabelledClaim
    ) -> Result[None, ClaimRefusedError]:
        try:
            with Activity(f"Labelling {request.ticket.root} as {request.label.root}").logged(
                logger
            ):
                tracker.add_label(request.ticket, request.label)
        except TicketTrackerError as error:
            return Err(
                ClaimRefusedError(
                    f"Could not label {request.ticket.root} as {request.label.root}."
                    f" Create the label or change claims.label. {error}"
                )
            )
        return Ok(None)

    @staticmethod
    def withdraw_holders_claims(
        registry: ClaimRegistry, ticket: IssueIdentifier, holder: ClaimHolder
    ) -> Result[None, TicketTrackerError]:
        match registry.claims(ticket):
            case Ok(held):
                for claim in held.root:
                    if claim.holder == holder:
                        registry.withdraw(ticket, claim.id)
                return Ok(None)
            case Err() as failed:
                return failed

    @staticmethod
    def release_claim(
        registry: ClaimRegistry, tracker: TicketTracker, request: LabelledClaim
    ) -> Result[None, TicketTrackerError]:
        with Activity(f"Releasing the claim on {request.ticket.root}").logged(logger):
            withdrawn = Claiming.withdraw_holders_claims(registry, request.ticket, request.holder)
            if isinstance(withdrawn, Err):
                return withdrawn
            left = registry.claims(request.ticket)
            if isinstance(left, Err):
                return left
            if left.value.root:
                return Ok(None)
            try:
                tracker.remove_label(request.ticket, request.label)
            except TicketTrackerError as error:
                logger.warning(
                    "Could not remove the %s label from %s: %s",
                    request.label.root,
                    request.ticket.root,
                    error,
                )
            return Ok(None)


class LabelledClaim(Model):
    ticket: IssueIdentifier
    holder: ClaimHolder
    label: LabelName

    @staticmethod
    def fake() -> LabelledClaim:
        return LabelledClaim(
            ticket=IssueIdentifier.fake(), holder=ClaimHolder.fake(), label=LabelName("claimed")
        )


class FakeClaimRegistry(ClaimRegistry):
    def __init__(self, claims: dict[IssueIdentifier, Claims] | None = None) -> None:
        self._claims = dict(claims or {})
        self._ids = count(1)

    @override
    def claims(self, ticket: IssueIdentifier) -> Result[Claims, TicketTrackerError]:
        return Ok(self._held(ticket))

    @override
    def post(self, ticket: IssueIdentifier, holder: ClaimHolder) -> ClaimId:
        posted = Claim(id=ClaimId(f"claim-{next(self._ids)}"), holder=holder)
        self._claims[ticket] = Claims((*self._held(ticket).root, posted))
        return posted.id

    @override
    def withdraw(self, ticket: IssueIdentifier, claim: ClaimId) -> None:
        self._claims[ticket] = Claims(
            tuple(held for held in self._held(ticket).root if held.id != claim)
        )

    def _held(self, ticket: IssueIdentifier) -> Claims:
        return self._claims.get(ticket, Claims(()))
