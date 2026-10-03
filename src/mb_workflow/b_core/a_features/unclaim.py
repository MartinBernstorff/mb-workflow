import logging
from typing import TYPE_CHECKING

from mb_workflow.b_core.c_secondary_ports.claims import Claiming

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.claims import ClaimRegistry
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.d_domain_model.config import ClaimSettings
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier

logger = logging.getLogger(__name__)


def unclaim_ticket(
    *,
    registry: ClaimRegistry,
    tracker: TicketTracker,
    claim_settings: ClaimSettings,
    ticket: IssueIdentifier,
) -> None:
    held = registry.claims(ticket)
    if held.root:
        Claiming.withdraw_claims(registry, ticket, held)
    else:
        logger.info("%s has no claim.", ticket.root)
    tracker.remove_label(ticket, claim_settings.label)
    logger.info("Removed the %s label from %s.", claim_settings.label.root, ticket.root)
