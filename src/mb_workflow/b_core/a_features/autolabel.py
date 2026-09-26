import logging
import re
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from mb_workflow.b_core.c_secondary_ports.issue_tracker import IssueTrackerError
from mb_workflow.b_core.d_domain_model.cache import CacheDirectory
from mb_workflow.b_core.d_domain_model.issue import (
    Issue,
    IssueFilter,
    IssueIdentifier,
    Issues,
    IssueText,
    LabelName,
    ProjectName,
    StatusName,
)
from mb_workflow.b_core.d_domain_model.outcome import Failed
from mb_workflow.d_lib.models import Model, Value

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.issue_tracker import IssueTracker

logger = logging.getLogger(__name__)


class UnknownLabelError(Exception):
    pass


class SkipCount(Value[int]):
    @staticmethod
    def fake() -> SkipCount:
        return SkipCount(1)


class SkipPhrase(Value[str]):
    @staticmethod
    def fake() -> SkipPhrase:
        return SkipReason.already_labelled.counted(SkipCount.fake())


class SkipReason(StrEnum):
    excluded_status = "excluded status"
    excluded_project = "excluded project"
    already_recorded = "already recorded"
    already_labelled = "already labelled"

    def counted(self, count: SkipCount) -> SkipPhrase:
        if count.root == 1:
            return SkipPhrase(f"{count.root} {self.value}")
        plural = {
            SkipReason.excluded_status: "excluded statuses",
            SkipReason.excluded_project: "excluded projects",
        }.get(self, self.value)
        return SkipPhrase(f"{count.root} {plural}")


class Excluded(Value[bool]):
    @staticmethod
    def fake() -> Excluded:
        return Excluded(True)


class ExcludePattern(Value[str]):
    @staticmethod
    def fake() -> ExcludePattern:
        return ExcludePattern("^BE[: ]|backend")

    def matches(self, text: IssueText) -> Excluded:
        return Excluded(re.search(self.root, text.root, re.IGNORECASE) is not None)


class Exclusions(Model):
    projects: ExcludePattern | None
    statuses: ExcludePattern | None

    @staticmethod
    def fake() -> Exclusions:
        return Exclusions(
            projects=ExcludePattern.fake(),
            statuses=ExcludePattern("done|canceled|duplicate|triage"),
        )

    def excludes_project(self, project: ProjectName | None) -> Excluded:
        if project is None or self.projects is None:
            return Excluded(False)
        return self.projects.matches(project)

    def excludes_status(self, status: StatusName) -> Excluded:
        if self.statuses is None:
            return Excluded(False)
        return self.statuses.matches(status)


class Recorded(Value[bool]):
    @staticmethod
    def fake() -> Recorded:
        return Recorded(True)


class LedgerText(Value[str]):
    @staticmethod
    def fake() -> LedgerText:
        return LedgerText(f"{IssueIdentifier.fake().root}\n")


class Ledger(Value[tuple[IssueIdentifier, ...]]):
    @staticmethod
    def fake() -> Ledger:
        return Ledger((IssueIdentifier.fake(),))

    @staticmethod
    def decode(text: LedgerText) -> Ledger:
        return Ledger(
            tuple(IssueIdentifier(line.strip()) for line in text.root.splitlines() if line.strip())
        )

    def encode(self) -> LedgerText:
        return LedgerText("".join(f"{issue.root}\n" for issue in self.root))

    def records(self, issue: IssueIdentifier) -> Recorded:
        return Recorded(issue in self.root)

    def extended(self, issues: tuple[IssueIdentifier, ...]) -> Ledger:
        added = tuple(issue for issue in issues if self.records(issue) == Recorded(False))
        return Ledger((*self.root, *dict.fromkeys(added)))


class LedgerName(Value[str]):
    @staticmethod
    def fake() -> LedgerName:
        return LedgerName.of(LabelName.fake())

    @staticmethod
    def of(label: LabelName) -> LedgerName:
        return LedgerName(re.sub(r"[^a-z0-9._-]+", "-", label.root.lower()))


class LedgerPath(Value[Path]):
    @staticmethod
    def fake() -> LedgerPath:
        return LedgerPath.of(CacheDirectory.fake(), LabelName.fake())

    @staticmethod
    def of(directory: CacheDirectory, label: LabelName) -> LedgerPath:
        return LedgerPath(directory.root / f"autolabel-{LedgerName.of(label).root}.txt")

    def read(self) -> Ledger:
        if not self.root.is_file():
            return Ledger(())
        return Ledger.decode(LedgerText(self.root.read_text()))

    def write(self, ledger: Ledger) -> None:
        self.root.parent.mkdir(parents=True, exist_ok=True)
        _ = self.root.write_text(ledger.encode().root)


class Criteria(Model):
    label: LabelName
    exclusions: Exclusions
    ledger: Ledger

    @staticmethod
    def fake() -> Criteria:
        return Criteria(label=LabelName.fake(), exclusions=Exclusions.fake(), ledger=Ledger.fake())

    def skipped(self, issue: Issue) -> SkipReason | None:
        if self.exclusions.excludes_status(issue.status).root:
            return SkipReason.excluded_status
        if self.exclusions.excludes_project(issue.project).root:
            return SkipReason.excluded_project
        if self.ledger.records(issue.identifier).root:
            return SkipReason.already_recorded
        if issue.labels.has(self.label).root:
            return SkipReason.already_labelled
        return None


class Decision(Model):
    issue: Issue
    skipped: SkipReason | None

    @staticmethod
    def fake() -> Decision:
        return Decision(issue=Issue.fake(), skipped=None)


class SkipTally(Model):
    reason: SkipReason
    count: SkipCount

    @staticmethod
    def fake() -> SkipTally:
        return SkipTally(reason=SkipReason.already_labelled, count=SkipCount.fake())


class Selection(Value[tuple[Decision, ...]]):
    @staticmethod
    def fake() -> Selection:
        return Selection((Decision.fake(),))

    @staticmethod
    def of(issues: Issues, criteria: Criteria) -> Selection:
        return Selection(
            tuple(Decision(issue=issue, skipped=criteria.skipped(issue)) for issue in issues.root)
        )

    def labellable(self) -> Issues:
        return Issues(tuple(decision.issue for decision in self.root if decision.skipped is None))

    def skips(self) -> tuple[SkipTally, ...]:
        counts = {
            reason: sum(1 for decision in self.root if decision.skipped == reason)
            for reason in SkipReason
        }
        return tuple(
            SkipTally(reason=reason, count=SkipCount(count))
            for reason, count in counts.items()
            if count > 0
        )


class Apply(Value[bool]):
    @staticmethod
    def fake() -> Apply:
        return Apply(False)


class SummaryLine(Value[str]):
    @staticmethod
    def fake() -> SummaryLine:
        return Outcome.fake().summary()


class AutolabelRequest(Model):
    label: LabelName
    wanted: IssueFilter
    exclusions: Exclusions
    apply: Apply

    @staticmethod
    def fake() -> AutolabelRequest:
        return AutolabelRequest(
            label=LabelName.fake(),
            wanted=IssueFilter.fake(),
            exclusions=Exclusions.fake(),
            apply=Apply.fake(),
        )


class Outcome(Model):
    selection: Selection
    applied: Apply
    labelled: tuple[IssueIdentifier, ...]
    failed: tuple[IssueIdentifier, ...]

    @staticmethod
    def fake() -> Outcome:
        return Outcome(
            selection=Selection.fake(),
            applied=Apply(True),
            labelled=(IssueIdentifier.fake(),),
            failed=(),
        )

    def failed_any(self) -> Failed:
        return Failed(len(self.failed) > 0)

    def chosen(self) -> tuple[IssueIdentifier, ...]:
        if self.applied.root:
            return self.labelled
        return self.selection.labellable().identifiers()

    def summary(self) -> SummaryLine:
        chosen = self.chosen()
        verb = "Labelled" if self.applied.root else "Would label"
        total = len(self.selection.root)
        parts = [f"{verb} {len(chosen)} of {total} issue{'' if total == 1 else 's'}"]
        skips = self.selection.skips()
        if len(skips) > 0:
            parts.append(
                "skipped " + ", ".join(tally.reason.counted(tally.count).root for tally in skips)
            )
        if len(self.failed) > 0:
            parts.append(f"{len(self.failed)} failed")
        return SummaryLine("; ".join(parts))

    def report(self) -> None:
        verb = "labelled" if self.applied.root else "would label"
        for issue in self.chosen():
            logger.info("%s %s", verb, issue.root)
        logger.info("%s", self.summary().root)
        if not self.applied.root:
            logger.info("Re-run with --apply to label them.")


def sweep(tracker: IssueTracker, request: AutolabelRequest, ledger: LedgerPath) -> Outcome:
    if not tracker.workspace_labels().has(request.label).root:
        raise UnknownLabelError(f"No label is named {request.label.root}.")

    recorded = ledger.read()
    issues = tracker.issues(request.wanted)
    logger.info(
        "Sweeping %s issues created since %s",
        len(issues.root),
        request.wanted.created_after.root.isoformat(),
    )

    criteria = Criteria(label=request.label, exclusions=request.exclusions, ledger=recorded)
    outcome = updated(tracker, Selection.of(issues, criteria), request)
    outcome.report()
    if request.apply.root and len(outcome.labelled) > 0:
        ledger.write(recorded.extended(outcome.labelled))
    return outcome


def updated(tracker: IssueTracker, selection: Selection, request: AutolabelRequest) -> Outcome:
    if not request.apply.root:
        return Outcome(selection=selection, applied=request.apply, labelled=(), failed=())

    added: list[IssueIdentifier] = []
    failed: list[IssueIdentifier] = []
    for issue in selection.labellable().root:
        try:
            tracker.add_label(issue.identifier, request.label)
        except IssueTrackerError as error:
            logger.error("%s could not be labelled: %s", issue.identifier.root, error)
            failed.append(issue.identifier)
        else:
            added.append(issue.identifier)
    return Outcome(
        selection=selection,
        applied=request.apply,
        labelled=tuple(added),
        failed=tuple(failed),
    )
