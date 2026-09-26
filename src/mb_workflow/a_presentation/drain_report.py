import logging
from typing import TYPE_CHECKING

from mb_workflow.a_presentation.console import Output

if TYPE_CHECKING:
    from mb_workflow.b_core.a_features.drain import DrainOutcome
    from mb_workflow.b_core.d_domain_model.flow import StateName
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.pool import PoolTickets

logger = logging.getLogger(__name__)


def pick_listing(ready: PoolTickets, flow_labels: FlowLabels) -> Output:
    return Output(
        "".join(
            f"{ticket.issue.identifier.root}\t{ticket.priority.name}\t{state_cell(ticket.flow_state(flow_labels)).root}\n"
            for ticket in ready.root
        )
    )


def state_cell(state: StateName | None) -> Output:
    return Output("-" if state is None else state.root)


def log_drain_outcome(outcome: DrainOutcome) -> None:
    if not outcome.picked.root:
        logger.info("Started no ticket; %s were ready.", len(outcome.ready.root))
        return
    logger.info(
        "Started %s.", ", ".join(identifier.root for identifier in outcome.picked.identifiers())
    )
