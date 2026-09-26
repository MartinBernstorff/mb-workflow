import logging
from itertools import count
from typing import Protocol, override

from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker, TicketTrackerError
from mb_workflow.b_core.d_domain_model.claim import (
    Claim,
    ClaimHolder,
    ClaimId,
    Claims,
    SettleTime,
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


class Pause(Protocol):
    def wait(self, duration: SettleTime) -> None: ...


class ClaimRequest(Model):
    ticket: IssueIdentifier
    status: IssueStatusName
    holder: ClaimHolder
    take_over: TakeOver
    settle: SettleTime

    @staticmethod
    def fake() -> ClaimRequest:
        return ClaimRequest(
            ticket=IssueIdentifier.fake(),
            status=IssueStatusName("Specced"),
            holder=ClaimHolder.fake(),
            take_over=TakeOver.fake(),
            settle=SettleTime.fake(),
        )


def claim_ticket(registry: ClaimRegistry, pause: Pause, request: ClaimRequest) -> None:
    held = registry.claims(request.ticket)
    current = held.holding(request.status)
    if current is not None and current.holder == request.holder:
        return
    if current is not None and not request.take_over.root:
        raise claimed_error(request.ticket, current)
    withdraw_claims(registry, request.ticket, held)

    # Every claimer posts before reading, so whoever reads after the pause sees the same earliest claim.
    posted = registry.post(request.ticket, request.holder)
    pause.wait(request.settle)
    settled = registry.claims(request.ticket)
    winner = settled.holding(request.status)
    if winner is not None and winner.id == posted:
        return
    if posted in settled.ids():
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


# Checked before claiming, so a doomed claim never withdraws another holder's claim.
def require_claim_label(tracker: TicketTracker, label: LabelName) -> None:
    if tracker.workspace_labels().matching(label) is None:
        raise ClaimRefusedError(
            f"No label is named {label.root}. Create the label or change claims.label."
        )


# The label is how in-progress tickets are found, so a claim that cannot be labelled is withdrawn.
def label_claim_or_withdraw(
    registry: ClaimRegistry, tracker: TicketTracker, request: LabelledClaim
) -> None:
    try:
        tracker.add_label(request.ticket, request.label)
    except TicketTrackerError as error:
        withdraw_holders_claims(registry, request.ticket, request.holder)
        raise ClaimRefusedError(
            f"Could not label {request.ticket.root} as {request.label.root}, so the claim was"
            f" withdrawn. Create the label or change claims.label. {error}"
        ) from error


class LabelledClaim(Model):
    ticket: IssueIdentifier
    holder: ClaimHolder
    label: LabelName

    @staticmethod
    def fake() -> LabelledClaim:
        return LabelledClaim(
            ticket=IssueIdentifier.fake(), holder=ClaimHolder.fake(), label=LabelName("claimed")
        )


def withdraw_holders_claims(
    registry: ClaimRegistry, ticket: IssueIdentifier, holder: ClaimHolder
) -> None:
    for held in registry.claims(ticket).root:
        if held.holder == holder:
            registry.withdraw(ticket, held.id)


def release_claim(registry: ClaimRegistry, tracker: TicketTracker, request: LabelledClaim) -> None:
    withdraw_holders_claims(registry, request.ticket, request.holder)
    if registry.claims(request.ticket).root:
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


class FakePause(Pause):
    def __init__(self) -> None:
        self._waited: list[SettleTime] = []

    @override
    def wait(self, duration: SettleTime) -> None:
        self._waited.append(duration)

    def waited(self) -> tuple[SettleTime, ...]:
        return tuple(self._waited)
