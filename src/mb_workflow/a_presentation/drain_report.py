import logging
from typing import TYPE_CHECKING, override

from mb_workflow.a_presentation.console import Output
from mb_workflow.b_core.a_features.drain_watch import DrainNarrator

if TYPE_CHECKING:
    from mb_workflow.b_core.a_features.drain import Changed, DrainOutcome
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


def log_pass(outcome: DrainOutcome) -> None:
    for unready in outcome.unready:
        logger.info("Skipped %s: %s.", unready.ticket.issue.identifier.root, unready.reason.root)
    if outcome.full is not None:
        logger.info(
            "The pool is full at %s tickets; leaving %s unstarted.",
            outcome.full.total.root,
            ", ".join(identifier.root for identifier in outcome.full.left.identifiers()),
        )
    for skip in outcome.skipped:
        logger.info("Skipped %s: %s.", skip.ticket.issue.identifier.root, skip.refusal.root)


def log_drain_outcome(outcome: DrainOutcome) -> None:
    if not outcome.picked.root:
        logger.info("Started no ticket; %s were ready.", len(outcome.ready.root))
        return
    logger.info(
        "Started %s.", ", ".join(identifier.root for identifier in outcome.picked.identifiers())
    )


# A watch logs a pass in full only when it differs from the last, so a quiet pool stays quiet.
class LoggingDrainNarrator(DrainNarrator):
    @override
    def passed(self, outcome: DrainOutcome, changed: Changed) -> None:
        if not changed.root:
            logger.info("No change; %s ready.", len(outcome.ready.root))
            return
        log_pass(outcome)
        log_drain_outcome(outcome)
