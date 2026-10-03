import logging
from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from mb_workflow.b_core.b_domain_services.label_selection import Selection
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTrackerError
from mb_workflow.b_core.d_domain_model.autolabel import AutoLabelCriteria, Exclusions
from mb_workflow.b_core.d_domain_model.issue import (
    CreatedAfter,
    Creator,
    IssueFilter,
    IssueIdentifier,
    LabelName,
)
from mb_workflow.b_core.d_domain_model.outcome import Failed
from mb_workflow.d_lib.models import Model, Value

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.ledger_store import LedgerStore
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker

logger = logging.getLogger(__name__)


class UnknownLabelError(Exception):
    pass


class DryRun(Value[bool]):
    @staticmethod
    def fake() -> DryRun:
        return DryRun(True)


class AutolabelRequest(Model):
    label: LabelName
    creator: Creator
    exclusions: Exclusions
    dry_run: DryRun

    @staticmethod
    def fake() -> AutolabelRequest:
        return AutolabelRequest(
            label=LabelName.fake(),
            creator=Creator.fake(),
            exclusions=Exclusions.fake(),
            dry_run=DryRun.fake(),
        )


class Outcome(Model):
    selection: Selection
    dry_run: DryRun
    labelled: tuple[IssueIdentifier, ...]
    failed: tuple[IssueIdentifier, ...]

    @staticmethod
    def fake() -> Outcome:
        return Outcome(
            selection=Selection.fake(),
            dry_run=DryRun(False),
            labelled=(IssueIdentifier.fake(),),
            failed=(),
        )

    def failed_any(self) -> Failed:
        return Failed(len(self.failed) > 0)

    def chosen(self) -> tuple[IssueIdentifier, ...]:
        if self.dry_run.root:
            return self.selection.labellable().identifiers()
        return self.labelled


class AutoLabelling:
    @staticmethod
    def label_eligible_issues(
        tracker: TicketTracker,
        ledger_store: LedgerStore,
        request: AutolabelRequest,
        window: CreatedAfter,
    ) -> Result[Outcome, TicketTrackerError | UnknownLabelError]:
        known = tracker.workspace_labels()
        if isinstance(known, Err):
            return known
        if not known.value.has(request.label).root:
            return Err(UnknownLabelError(f"No label is named {request.label.root}."))

        recorded = ledger_store.read(request.label)
        issues = tracker.list_issues(IssueFilter(creator=request.creator, created_after=window))
        if isinstance(issues, Err):
            return issues
        logger.info(
            "Sweeping %s issues created since %s", len(issues.value.root), window.root.isoformat()
        )

        group = tracker.label_group(request.label)
        if isinstance(group, Err):
            return group
        criteria = AutoLabelCriteria(
            label=request.label,
            exclusions=request.exclusions,
            ledger=recorded,
            group=group.value,
        )
        outcome = AutoLabelling.add_label_to_eligible(
            tracker, Selection.of(issues.value, criteria), request
        )

        if not request.dry_run.root and len(outcome.labelled) > 0:
            ledger_store.write(request.label, recorded.extended(outcome.labelled))

        return Ok(outcome)

    @staticmethod
    def add_label_to_eligible(
        tracker: TicketTracker, selection: Selection, request: AutolabelRequest
    ) -> Outcome:
        if request.dry_run.root:
            return Outcome(selection=selection, dry_run=request.dry_run, labelled=(), failed=())

        added: list[IssueIdentifier] = []
        failed: list[IssueIdentifier] = []
        for issue in selection.labellable().root:
            try:
                tracker.add_label(issue.identifier, request.label)
            except TicketTrackerError as error:
                logger.error("%s could not be labelled: %s", issue.identifier.root, error)
                failed.append(issue.identifier)
            else:
                added.append(issue.identifier)
        return Outcome(
            selection=selection,
            dry_run=request.dry_run,
            labelled=tuple(added),
            failed=tuple(failed),
        )
