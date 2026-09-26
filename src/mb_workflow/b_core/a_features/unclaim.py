import logging
from typing import TYPE_CHECKING

from mb_workflow.b_core.c_secondary_ports.claims import withdraw_claims

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.claims import ClaimRegistry
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier

logger = logging.getLogger(__name__)


def unclaim_ticket(registry: ClaimRegistry, ticket: IssueIdentifier) -> None:
    held = registry.claims(ticket)
    if not held.root:
        logger.info("%s has no claim.", ticket.root)
        return
    withdraw_claims(registry, ticket, held)
