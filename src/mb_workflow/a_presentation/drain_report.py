import logging
from typing import TYPE_CHECKING

from mb_workflow.a_presentation.console import Output

if TYPE_CHECKING:
    from mb_workflow.b_core.a_features.drain import DrainOutcome
    from mb_workflow.b_core.d_domain_model.pool import PoolTickets

logger = logging.getLogger(__name__)


def pick_listing(ready: PoolTickets) -> Output:
    return Output(
        "".join(
            f"{ticket.issue.identifier.root}\t{ticket.priority.name}\t{ticket.flow_state().root}\n"
            for ticket in ready.root
        )
    )


def log_drain_outcome(outcome: DrainOutcome) -> None:
    if not outcome.picked.root:
        logger.info("Started no ticket; %s were ready.", len(outcome.ready.root))
        return
    logger.info(
        "Started %s.", ", ".join(identifier.root for identifier in outcome.picked.identifiers())
    )
