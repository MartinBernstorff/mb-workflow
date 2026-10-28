import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Never, override

from safe_result import Err, Ok, Result

from mb_workflow.b_core.c_secondary_ports.claims import Claiming, ClaimLostError, ClaimRefusedError
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTrackerError
from mb_workflow.b_core.d_domain_model.claim import Posted
from mb_workflow.b_core.d_domain_model.issue import Cleared, IssueUpdate
from mb_workflow.d_lib.logging import Activity
from mb_workflow.d_lib.saga import Saga, SagaStep

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.claims import ClaimRegistry, ClaimRequest
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.d_domain_model.config import WorkspaceSettings
    from mb_workflow.b_core.d_domain_model.issue import Assignee, IssueIdentifier

logger = logging.getLogger(__name__)


class TicketTaking:
    # Shared by every command that puts a ticket in a worktree: claim it and assign it.
    @staticmethod
    def take_ticket(
        *,
        claims: ClaimRegistry,
        tracker: TicketTracker,
        workspace: WorkspaceSettings,
        request: ClaimRequest,
        previous: Assignee | None,
    ) -> Result[None, TicketTrackerError | ClaimRefusedError]:
        return Saga.run(
            TicketTaking.saga_steps(
                claims=claims,
                tracker=tracker,
                workspace=workspace,
                request=request,
                previous=previous,
            )
        )

    # `previous` is the assignee before taking, restored when a later step fails.
    @staticmethod
    def saga_steps(
        *,
        claims: ClaimRegistry,
        tracker: TicketTracker,
        workspace: WorkspaceSettings,
        request: ClaimRequest,
        previous: Assignee | None,
    ) -> tuple[SagaStep[TicketTrackerError | ClaimRefusedError], ...]:
        return (
            ClaimStep(claims, request),
            AssignmentStep(tracker, request.ticket, workspace.assignee, previous),
        )


# Reverting withdraws only this holder's claims; rival claims withdrawn by a takeover stay withdrawn.
# Mutable, as it holds whether it posted a claim, so revert withdraws only a claim it made.
@dataclass
class ClaimStep(SagaStep[TicketTrackerError | ClaimLostError]):
    registry: ClaimRegistry
    request: ClaimRequest
    _posted: Posted = field(default=Posted(False), init=False)

    @override
    def apply(self) -> Result[None, TicketTrackerError | ClaimLostError]:
        with Activity(
            f"Claiming {self.request.ticket.root} for worktree"
            f" {self.request.holder.worktree.root} on {self.request.holder.host.root}"
        ).logged(logger):
            claimed = Claiming.claim_ticket(self.registry, self.request)
        match claimed:
            case Ok(posted):
                self._posted = posted
                return Ok(None)
            case Err() as failed:
                return failed

    # A claim this holder held before taking is left in place.
    @override
    def revert(self) -> Result[None, Exception]:
        if not self._posted.root:
            return Ok(None)
        with Activity(f"Withdrawing our claim on {self.request.ticket.root}").logged(logger):
            return Claiming.withdraw_holders_claims(
                self.registry, self.request.ticket, self.request.holder
            )


@dataclass(frozen=True)
class AssignmentStep(SagaStep[Never]):
    tracker: TicketTracker
    ticket: IssueIdentifier
    assignee: Assignee
    previous: Assignee | None

    # Assignment is a convenience, not the point of taking a ticket, so never fail the run over it.
    @override
    def apply(self) -> Result[None, Never]:
        with Activity(f"Assigning {self.ticket.root} to {self.assignee.root}").logged(logger):
            assigned = self.tracker.assign(self.ticket, self.assignee)
        if isinstance(assigned, Err):
            logger.warning(
                "Could not assign %s to %s: %s",
                self.ticket.root,
                self.assignee.root,
                assigned.error,
            )
        return Ok(None)

    @override
    def revert(self) -> Result[None, Exception]:
        if self.previous is None:
            with Activity(f"Unassigning {self.ticket.root}").logged(logger):
                return self.tracker.update_issue(
                    self.ticket,
                    IssueUpdate.nothing().model_copy(update={"assignee": Cleared()}),
                )
        with Activity(f"Assigning {self.ticket.root} back to {self.previous.root}").logged(logger):
            return self.tracker.assign(self.ticket, self.previous)
