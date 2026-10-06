import logging
import re
from typing import TYPE_CHECKING, override

from mb_workflow.a_presentation.console import Output, write
from mb_workflow.b_core.a_features.autolabel import DryRun
from mb_workflow.b_core.a_features.drain_watch import DrainNarrator
from mb_workflow.b_core.d_domain_model.pool import PoolTicket
from mb_workflow.d_lib.models import Model, Value

if TYPE_CHECKING:
    from mb_workflow.b_core.a_features.drain import Changed, DrainOutcome
    from mb_workflow.b_core.d_domain_model.flow import StateName
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels

logger = logging.getLogger(__name__)


class Cell(Value[str]):
    @staticmethod
    def fake() -> Cell:
        return Cell("started")


class Started(Value[bool]):
    @staticmethod
    def fake() -> Started:
        return Started(True)


class SummaryRow(Model):
    ticket: PoolTicket
    started: Started
    outcome: Cell

    @staticmethod
    def fake() -> SummaryRow:
        return SummaryRow(ticket=PoolTicket.fake(), started=Started.fake(), outcome=Cell.fake())

    # Both marks fill two terminal columns, so the cells after them line up.
    def mark(self) -> Cell:
        return Cell("✅" if self.started.root else "· ")

    def cells(self, flow_labels: FlowLabels) -> tuple[Cell, ...]:
        return (
            Cell(self.ticket.issue.identifier.root),
            Cell(self.ticket.priority.name),
            DrainReport.state_cell(self.ticket.flow_state(flow_labels).unwrap_or(None)),
            self.outcome,
        )


class DrainReport:
    @staticmethod
    def state_cell(state: StateName | None) -> Cell:
        return Cell("-" if state is None else state.root)

    @staticmethod
    def rows(outcome: DrainOutcome, dry_run: DryRun) -> tuple[SummaryRow, ...]:
        start = "would start" if dry_run.root else "started"
        overrides = {override.ticket.issue.identifier: override for override in outcome.overridden}
        full = (
            ()
            if outcome.full is None
            else tuple(
                SummaryRow(
                    ticket=ticket,
                    started=Started(False),
                    outcome=Cell(f"not started: the pool is full at {outcome.full.total.root}"),
                )
                for ticket in outcome.full.left.root
            )
        )
        return (
            *(
                SummaryRow(
                    ticket=ticket,
                    started=Started(True),
                    outcome=Cell(
                        start
                        if (override := overrides.get(ticket.issue.identifier)) is None
                        else f"{start} although {override.refusal.root}"
                    ),
                )
                for ticket in outcome.picked.root
            ),
            *(
                SummaryRow(
                    ticket=unready.ticket,
                    started=Started(False),
                    outcome=Cell(f"not ready: {unready.reason.root}"),
                )
                for unready in outcome.unready
            ),
            *(
                SummaryRow(
                    ticket=skip.ticket,
                    started=Started(False),
                    outcome=Cell(f"skipped: {skip.refusal.root}"),
                )
                for skip in outcome.skipped
            ),
            *(
                SummaryRow(
                    ticket=lost.ticket,
                    started=Started(False),
                    outcome=Cell(f"lost: {lost.reason.root}"),
                )
                for lost in outcome.lost
            ),
            *full,
        )

    # Digit runs are padded to one width before comparing, so MB-9 sorts before MB-10.
    @staticmethod
    def in_ticket_order(rows: tuple[SummaryRow, ...]) -> tuple[SummaryRow, ...]:
        width = max((len(row.ticket.issue.identifier.root) for row in rows), default=0)
        keyed = sorted(
            (
                "".join(
                    part.zfill(width) if part.isdigit() else part
                    for part in re.split(r"(\d+)", row.ticket.issue.identifier.root)
                ),
                position,
            )
            for position, row in enumerate(rows)
        )
        return tuple(rows[position] for _, position in keyed)

    @staticmethod
    def summary(outcome: DrainOutcome, flow_labels: FlowLabels, dry_run: DryRun) -> Output:
        rows = DrainReport.in_ticket_order(DrainReport.rows(outcome, dry_run))
        started = sum(1 for row in rows if row.started.root)
        verb = "Would start" if dry_run.root else "Started"
        footer = f"{verb} {started} of {len(rows)}.\n"
        if not rows:
            return Output(footer)
        header = (Cell("Ticket"), Cell("Priority"), Cell("State"), Cell("Outcome"))
        body = tuple((row.mark(), row.cells(flow_labels)) for row in rows)
        table = ((Cell("  "), header), *body)
        widths = tuple(
            max(len(cells[column].root) for _, cells in table) for column in range(len(header))
        )
        lines = (
            " ".join(
                (
                    mark.root,
                    "  ".join(
                        cell.root.ljust(width) for cell, width in zip(cells, widths, strict=True)
                    ),
                )
            ).rstrip()
            for mark, cells in table
        )
        return Output("".join(f"{line}\n" for line in lines) + "\n" + footer)


# A watch prints a pass's summary only when it differs from the last, so a quiet pool stays quiet.
class ConsoleDrainNarrator(DrainNarrator):
    def __init__(self, flow_labels: FlowLabels) -> None:
        self._flow_labels = flow_labels

    @override
    def passed(self, outcome: DrainOutcome, changed: Changed) -> None:
        if not changed.root:
            logger.info("No change; %s ready.", len(outcome.ready.root))
            return
        write(DrainReport.summary(outcome, self._flow_labels, DryRun(False)))
