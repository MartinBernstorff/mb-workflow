import logging
from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from mb_workflow.b_core.c_secondary_ports.claims import Claiming

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.claims import ClaimRegistry
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTrackerError
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier

logger = logging.getLogger(__name__)


class TicketUnclaiming:
    @staticmethod
    def unclaim_ticket(
        *, registry: ClaimRegistry, ticket: IssueIdentifier
    ) -> Result[None, TicketTrackerError]:
        held = registry.claims(ticket)
        if isinstance(held, Err):
            return held
        if not held.value.root:
            logger.info("%s has no claim.", ticket.root)
            return Ok(None)
        return Claiming.withdraw_claims(registry, ticket, held.value)
