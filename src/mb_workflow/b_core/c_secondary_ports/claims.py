import logging
from itertools import count
from typing import Protocol, override

from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker, TicketTrackerError
from mb_workflow.b_core.d_domain_model.claim import (
    Claim,
    ClaimHolder,
    ClaimId,
    Claims,
    TakeOver,
)
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier, IssueStatusName, LabelName
from mb_workflow.d_lib.models import Model

logger = logging.getLogger(__name__)


class ClaimRefusedError(Exception):
    pass


class ClaimRegistry(Protocol):
    def claims(self, ticket: IssueIdentifier) -> Claims: ...

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


def claim_ticket(registry: ClaimRegistry, request: ClaimRequest) -> None:
    held = registry.claims(request.ticket)
    current = held.holding(request.status)
    if current is not None and current.holder == request.holder:
        return
    if current is not None and not request.take_over.root:
        raise claimed_error(request.ticket, current)
    withdraw_claims(registry, request.ticket, held)

    # Every claimer posts before reading, so each reads back the same earliest claim, provided Linear serves a just-posted comment at once.
    posted = registry.post(request.ticket, request.holder)
    read_back = registry.claims(request.ticket)
    winner = read_back.holding(request.status)
    if winner is not None and winner.id == posted:
        return
    if posted in read_back.ids():
        registry.withdraw(request.ticket, posted)
    if winner is None:
        raise ClaimRefusedError(f"Our claim on {request.ticket.root} was withdrawn by another.")
    raise claimed_error(request.ticket, winner)


def withdraw_claims(registry: ClaimRegistry, ticket: IssueIdentifier, held: Claims) -> None:
    for claim in held.root:
        logger.info(
            "Withdrawing the claim of worktree %s on %s.",
            claim.holder.worktree.root,
            claim.holder.host.root,
        )
        registry.withdraw(ticket, claim.id)


def claimed_error(ticket: IssueIdentifier, holder: Claim) -> ClaimRefusedError:
    return ClaimRefusedError(
        f"{ticket.root} is claimed by worktree {holder.holder.worktree.root}"
        f" on {holder.holder.host.root}. Pass --force to take the claim over."
    )


# The label only makes the claim visible; the comment is the claim, so a failed label never fails it.
def add_claim_label(
    tracker: TicketTracker, ticket: IssueIdentifier, label: LabelName | None
) -> None:
    if label is None:
        return
    try:
        tracker.add_label(ticket, label)
    except TicketTrackerError as error:
        logger.warning("Could not label %s as %s: %s", ticket.root, label.root, error)


class ReleaseRequest(Model):
    ticket: IssueIdentifier
    holder: ClaimHolder
    label: LabelName | None

    @staticmethod
    def fake() -> ReleaseRequest:
        return ReleaseRequest(
            ticket=IssueIdentifier.fake(), holder=ClaimHolder.fake(), label=LabelName("claimed")
        )


def release_claim(registry: ClaimRegistry, tracker: TicketTracker, request: ReleaseRequest) -> None:
    for held in registry.claims(request.ticket).root:
        if held.holder == request.holder:
            registry.withdraw(request.ticket, held.id)
    if request.label is None or registry.claims(request.ticket).root:
        return
    try:
        tracker.remove_label(request.ticket, request.label)
    except TicketTrackerError as error:
        logger.warning(
            "Could not remove the %s label from %s: %s",
            request.label.root,
            request.ticket.root,
            error,
        )


class FakeClaimRegistry(ClaimRegistry):
    def __init__(self, claims: dict[IssueIdentifier, Claims] | None = None) -> None:
        self._claims = dict(claims or {})
        self._ids = count(1)

    @override
    def claims(self, ticket: IssueIdentifier) -> Claims:
        return self._claims.get(ticket, Claims(()))

    @override
    def post(self, ticket: IssueIdentifier, holder: ClaimHolder) -> ClaimId:
        posted = Claim(id=ClaimId(f"claim-{next(self._ids)}"), holder=holder)
        self._claims[ticket] = Claims((*self.claims(ticket).root, posted))
        return posted.id

    @override
    def withdraw(self, ticket: IssueIdentifier, claim: ClaimId) -> None:
        self._claims[ticket] = Claims(
            tuple(held for held in self.claims(ticket).root if held.id != claim)
        )
