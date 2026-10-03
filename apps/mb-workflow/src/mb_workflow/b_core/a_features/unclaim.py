import logging
from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from mb_workflow.b_core.c_secondary_ports.claims import Claiming

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.claims import ClaimRegistry
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
        TicketTracker,
        TicketTrackerError,
    )
    from mb_workflow.b_core.d_domain_model.config import ClaimSettings
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier

logger = logging.getLogger(__name__)


class TicketUnclaiming:
    @staticmethod
    def unclaim_ticket(
        *,
        registry: ClaimRegistry,
        tracker: TicketTracker,
        claim_settings: ClaimSettings,
        ticket: IssueIdentifier,
    ) -> Result[None, TicketTrackerError]:
        held = registry.claims(ticket)
        if isinstance(held, Err):
            return held
        if held.value.root:
            Claiming.withdraw_claims(registry, ticket, held.value)
        else:
            logger.info("%s has no claim.", ticket.root)
        tracker.remove_label(ticket, claim_settings.label)
        logger.info("Removed the %s label from %s.", claim_settings.label.root, ticket.root)
        return Ok(None)
