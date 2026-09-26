import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.claims import ClaimRegistry
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier

logger = logging.getLogger(__name__)


def unclaim_ticket(registry: ClaimRegistry, ticket: IssueIdentifier) -> None:
    held = registry.claims(ticket)
    for claim in held.root:
        logger.info(
            "Releasing the claim of worktree %s on %s.",
            claim.holder.worktree.root,
            claim.holder.host.root,
        )
        registry.withdraw(ticket, claim.id)
    if not held.root:
        logger.info("%s holds no claim.", ticket.root)
