import logging
from typing import TYPE_CHECKING

from mb_workflow.b_core.c_secondary_ports.claims import Claiming, LabelledClaim
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTrackerError
from mb_workflow.d_lib.logging import Activity

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.claims import ClaimRegistry, ClaimRequest
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.d_domain_model.config import ClaimSettings, WorkspaceSettings

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
    ) -> None:
        Claiming.require_claim_label(tracker, claim_settings.label)
        with Activity(
            f"claiming {request.ticket.root} for worktree {request.holder.worktree.root}"
            f" on {request.holder.host.root}"
        ).logged(logger):
            Claiming.claim_ticket(claims, request)
        Claiming.label_claim_or_withdraw(
            claims,
            tracker,
            LabelledClaim(ticket=request.ticket, holder=request.holder, label=claim_settings.label),
        )

        # Assignment is a convenience, not the point of taking a ticket, so never fail the run over it.
        try:
            with Activity(f"assigning {request.ticket.root} to {workspace.assignee.root}").logged(
                logger
            ):
                tracker.assign(request.ticket, workspace.assignee)
        except TicketTrackerError as error:
            logger.warning(
                "Could not assign %s to %s: %s",
                request.ticket.root,
                workspace.assignee.root,
                error,
            )
