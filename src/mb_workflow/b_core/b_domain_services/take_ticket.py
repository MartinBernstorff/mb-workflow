import logging
from typing import TYPE_CHECKING, override

from safe_result import Err, Ok, Result

from mb_workflow.b_core.c_secondary_ports.claims import (
    Claiming,
    ClaimRefusedError,
    LabelledClaim,
)
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTrackerError
from mb_workflow.b_core.d_domain_model.claim import Posted
from mb_workflow.b_core.d_domain_model.issue import Cleared, IssueUpdate
from mb_workflow.d_lib.logging import Activity
from mb_workflow.d_lib.models import Value
from mb_workflow.d_lib.saga import Saga, SagaStep

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.claims import ClaimRegistry, ClaimRequest
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.d_domain_model.config import ClaimSettings, WorkspaceSettings
    from mb_workflow.b_core.d_domain_model.issue import Assignee, IssueIdentifier

logger = logging.getLogger(__name__)


class TicketTaking:
    # Shared by every command that puts a ticket in a worktree: claim it, label the claim, assign it.
    @staticmethod
    def take_ticket(
        *,
        claims: ClaimRegistry,
        tracker: TicketTracker,
        workspace: WorkspaceSettings,
        claim_settings: ClaimSettings,
        request: ClaimRequest,
        previous: Assignee | None,
    ) -> None:
        Saga.run(
            TicketTaking.saga_steps(
                claims=claims,
                tracker=tracker,
                workspace=workspace,
                claim_settings=claim_settings,
                request=request,
                previous=previous,
            )
        ).unwrap()

    # `previous` is the assignee before taking, restored when a later step fails.
    @staticmethod
    def saga_steps(
        *,
        claims: ClaimRegistry,
        tracker: TicketTracker,
        workspace: WorkspaceSettings,
        claim_settings: ClaimSettings,
        request: ClaimRequest,
        previous: Assignee | None,
    ) -> tuple[SagaStep, ...]:
        Claiming.require_claim_label(tracker, claim_settings.label)
        labelled = LabelledClaim(
            ticket=request.ticket, holder=request.holder, label=claim_settings.label
        )
        return (
            ClaimStep(claims, request),
            ClaimLabelStep(claims, tracker, labelled),
            AssignmentStep(tracker, request.ticket, workspace.assignee, previous),
        )


# Reverting withdraws only this holder's claims; rival claims withdrawn by a takeover stay withdrawn.
class ClaimStep(SagaStep):
    def __init__(self, registry: ClaimRegistry, request: ClaimRequest) -> None:
        self._registry = registry
        self._request = request
        self._posted = Posted(False)

    @override
    def apply(self) -> Result[None, Exception]:
        try:
            with Activity(
                f"Claiming {self._request.ticket.root} for worktree"
                f" {self._request.holder.worktree.root} on {self._request.holder.host.root}"
            ).logged(logger):
                self._posted = Claiming.claim_ticket(self._registry, self._request)
        except (ClaimRefusedError, TicketTrackerError) as error:
            return Err(error)
        return Ok(None)

    # A claim this holder held before taking is left in place.
    @override
    def revert(self) -> Result[None, Exception]:
        if not self._posted.root:
            return Ok(None)
        try:
            with Activity(f"Withdrawing our claim on {self._request.ticket.root}").logged(logger):
                Claiming.withdraw_holders_claims(
                    self._registry, self._request.ticket, self._request.holder
                )
        except TicketTrackerError as error:
            return Err(error)
        return Ok(None)


class ClaimLabelStep(SagaStep):
    def __init__(
        self, registry: ClaimRegistry, tracker: TicketTracker, request: LabelledClaim
    ) -> None:
        self._registry = registry
        self._tracker = tracker
        self._request = request
        self._added = Added(False)

    @override
    def apply(self) -> Result[None, Exception]:
        try:
            labels = self._tracker.read_issue(self._request.ticket).labels
        except TicketTrackerError as error:
            return Err(error)
        if labels.has(self._request.label).root:
            return Ok(None)
        labelled = Claiming.label_claim(self._tracker, self._request)
        self._added = Added(labelled.is_ok())
        return labelled

    # The label marks every claim on the ticket, so it stays while another holder claims it.
    @override
    def revert(self) -> Result[None, Exception]:
        if not self._added.root:
            return Ok(None)
        try:
            held = self._registry.claims(self._request.ticket)
            if any(claim.holder != self._request.holder for claim in held.root):
                return Ok(None)
            with Activity(
                f"Removing the {self._request.label.root} label from {self._request.ticket.root}"
            ).logged(logger):
                self._tracker.remove_label(self._request.ticket, self._request.label)
        except TicketTrackerError as error:
            return Err(error)
        return Ok(None)


# Whether the step put the label on, rather than finding it there already.
class Added(Value[bool]):
    @staticmethod
    def fake() -> Added:
        return Added(True)


class AssignmentStep(SagaStep):
    def __init__(
        self,
        tracker: TicketTracker,
        ticket: IssueIdentifier,
        assignee: Assignee,
        previous: Assignee | None,
    ) -> None:
        self._tracker = tracker
        self._ticket = ticket
        self._assignee = assignee
        self._previous = previous

    # Assignment is a convenience, not the point of taking a ticket, so never fail the run over it.
    @override
    def apply(self) -> Result[None, Exception]:
        try:
            with Activity(f"Assigning {self._ticket.root} to {self._assignee.root}").logged(logger):
                self._tracker.assign(self._ticket, self._assignee)
        except TicketTrackerError as error:
            logger.warning(
                "Could not assign %s to %s: %s", self._ticket.root, self._assignee.root, error
            )
        return Ok(None)

    @override
    def revert(self) -> Result[None, Exception]:
        try:
            if self._previous is None:
                with Activity(f"Unassigning {self._ticket.root}").logged(logger):
                    self._tracker.update_issue(
                        self._ticket,
                        IssueUpdate.nothing().model_copy(update={"assignee": Cleared()}),
                    )
            else:
                with Activity(
                    f"Assigning {self._ticket.root} back to {self._previous.root}"
                ).logged(logger):
                    self._tracker.assign(self._ticket, self._previous)
        except TicketTrackerError as error:
            return Err(error)
        return Ok(None)
