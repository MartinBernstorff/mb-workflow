import logging
from typing import TYPE_CHECKING

from mb_workflow.b_core.c_secondary_ports.claims import Claiming, LabelledClaim
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTrackerError

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
        Claiming.claim_ticket(claims, request)
        logger.info(
            "Claimed %s for worktree %s on %s.",
            request.ticket.root,
            request.holder.worktree.root,
            request.holder.host.root,
        )
        Claiming.label_claim_or_withdraw(
            claims,
            tracker,
            LabelledClaim(ticket=request.ticket, holder=request.holder, label=claim_settings.label),
        )

        # Assignment is a convenience, not the point of taking a ticket, so never fail the run over it.
        try:
            tracker.assign(request.ticket, workspace.assignee)
        except TicketTrackerError as error:
            logger.warning(
                "Could not assign %s to %s: %s",
                request.ticket.root,
                workspace.assignee.root,
                error,
            )
        else:
            logger.info("Assigned %s to %s.", request.ticket.root, workspace.assignee.root)
