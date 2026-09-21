import logging
import re
from enum import StrEnum
from pathlib import Path
from subprocess import CalledProcessError
from typing import TYPE_CHECKING

from pydantic import ValidationError

from mb_workflow.a_presentation.console import ExitCode
from mb_workflow.b_core.cache import CacheDirectory
from mb_workflow.b_core.issue import IssueIdentifier
from mb_workflow.c_infrastructure.linear import (
    IssueQuery,
    IssueText,
    LabelName,
    Linear,
    ListedIssue,
    ListedIssues,
    Project,
    StatusName,
)
from mb_workflow.d_lib.models import Model, Value

if TYPE_CHECKING:
    from mb_workflow.c_infrastructure.shell import Shell

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

    def excludes_project(self, project: Project | None) -> Excluded:
        if project is None or self.projects is None:
            return Excluded(False)
        return self.projects.matches(project.name)

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

    def skipped(self, issue: ListedIssue) -> SkipReason | None:
        if self.exclusions.excludes_status(issue.status).root:
            return SkipReason.excluded_status
        if self.exclusions.excludes_project(issue.project).root:
            return SkipReason.excluded_project
        if self.ledger.records(issue.identifier).root:
            return SkipReason.already_recorded
        if self.label in issue.label_names().root:
            return SkipReason.already_labelled
        return None


class Decision(Model):
    issue: ListedIssue
    skipped: SkipReason | None

    @staticmethod
    def fake() -> Decision:
        return Decision(issue=ListedIssue.fake(), skipped=None)


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
    def of(issues: ListedIssues, criteria: Criteria) -> Selection:
        return Selection(
            tuple(Decision(issue=issue, skipped=criteria.skipped(issue)) for issue in issues.root)
        )

    def labellable(self) -> ListedIssues:
        return ListedIssues(
            tuple(decision.issue for decision in self.root if decision.skipped is None)
        )

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
    query: IssueQuery
    exclusions: Exclusions
    apply: Apply

    @staticmethod
    def fake() -> AutolabelRequest:
        return AutolabelRequest(
            label=LabelName.fake(),
            query=IssueQuery.fake(),
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

    def exit_code(self) -> ExitCode:
        return ExitCode(1 if len(self.failed) > 0 else 0)

    def chosen(self) -> tuple[IssueIdentifier, ...]:
        if self.applied.root:
            return self.labelled
        return tuple(issue.identifier for issue in self.selection.labellable().root)

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


def autolabel(shell: Shell, request: AutolabelRequest, ledger: LedgerPath) -> ExitCode:
    try:
        return swept(Linear(shell), request, ledger)
    except FileNotFoundError as error:
        logger.error("%s is not installed or not on PATH.", error.filename)
        return ExitCode(1)
    except (CalledProcessError, UnknownLabelError, ValidationError, re.error, ValueError) as error:
        logger.error("%s", error)
        return ExitCode(1)


def swept(linear: Linear, request: AutolabelRequest, ledger: LedgerPath) -> ExitCode:
    if not linear.workspace_labels().has(request.label).root:
        raise UnknownLabelError(f"No Linear label is named {request.label.root}.")

    recorded = ledger.read()
    issues = linear.issues(request.query)
    logger.info(
        "Sweeping %s issues created since %s",
        len(issues.root),
        request.query.created_after.root.isoformat(),
    )

    criteria = Criteria(label=request.label, exclusions=request.exclusions, ledger=recorded)
    outcome = updated(linear, Selection.of(issues, criteria), request)
    outcome.report()
    if request.apply.root and len(outcome.labelled) > 0:
        ledger.write(recorded.extended(outcome.labelled))
    return outcome.exit_code()


def updated(linear: Linear, selection: Selection, request: AutolabelRequest) -> Outcome:
    if not request.apply.root:
        return Outcome(selection=selection, applied=request.apply, labelled=(), failed=())

    added: list[IssueIdentifier] = []
    failed: list[IssueIdentifier] = []
    for issue in selection.labellable().root:
        try:
            linear.add_label(issue.identifier, request.label)
        except CalledProcessError as error:
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
