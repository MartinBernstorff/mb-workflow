import re
from enum import StrEnum

from mb_workflow.b_core.d_domain_model.issue import (
    Issue,
    IssueIdentifier,
    IssueStatusName,
    IssueText,
    LabelName,
    ProjectName,
)
from mb_workflow.d_lib.models import Model, Value


class SkipReason(StrEnum):
    excluded_status = "excluded status"
    excluded_project = "excluded project"
    already_recorded = "already recorded"
    already_labelled = "already labelled"


class SkipCount(Value[int]):
    @staticmethod
    def fake() -> SkipCount:
        return SkipCount(1)


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

    def excludes_status(self, status: IssueStatusName) -> Excluded:
        if self.statuses is None:
            return Excluded(False)
        return self.statuses.matches(status)


class Recorded(Value[bool]):
    @staticmethod
    def fake() -> Recorded:
        return Recorded(True)


class Ledger(Value[tuple[IssueIdentifier, ...]]):
    @staticmethod
    def fake() -> Ledger:
        return Ledger((IssueIdentifier.fake(),))

    def records(self, issue: IssueIdentifier) -> Recorded:
        return Recorded(issue in self.root)

    def extended(self, issues: tuple[IssueIdentifier, ...]) -> Ledger:
        added = tuple(issue for issue in issues if self.records(issue) == Recorded(False))
        return Ledger((*self.root, *dict.fromkeys(added)))


class AutoLabelCriteria(Model):
    label: LabelName
    exclusions: Exclusions
    ledger: Ledger

    @staticmethod
    def fake() -> AutoLabelCriteria:
        return AutoLabelCriteria(
            label=LabelName.fake(), exclusions=Exclusions.fake(), ledger=Ledger.fake()
        )

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
