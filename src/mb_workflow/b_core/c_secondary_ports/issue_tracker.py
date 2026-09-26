from typing import Protocol

from mb_workflow.b_core.d_domain_model.issue import (
    Assignee,
    CreatedOn,
    Creator,
    Issue,
    IssueFilter,
    IssueIdentifier,
    Issues,
    LabelName,
    LabelNames,
)
from mb_workflow.d_lib.models import Model


class IssueTrackerError(Exception):
    pass


class IssueTracker(Protocol):
    def workspace_labels(self) -> LabelNames: ...

    def issues(self, wanted: IssueFilter) -> Issues: ...

    def read(self, issue: IssueIdentifier) -> Issue: ...

    def add_label(self, issue: IssueIdentifier, label: LabelName) -> None: ...

    def set_labels(self, issue: IssueIdentifier, labels: LabelNames) -> None: ...

    def assign(self, issue: IssueIdentifier, assignee: Assignee) -> None: ...


class TrackedIssue(Model):
    issue: Issue
    creator: Creator
    created_on: CreatedOn

    @staticmethod
    def fake() -> TrackedIssue:
        return TrackedIssue(issue=Issue.fake(), creator=Creator.fake(), created_on=CreatedOn.fake())


class FakeIssueTracker:
    def __init__(self, labels: LabelNames, issues: tuple[TrackedIssue, ...]) -> None:
        self._labels = labels
        self._issues = {tracked.issue.identifier: tracked for tracked in issues}

    def workspace_labels(self) -> LabelNames:
        return self._labels

    def issues(self, wanted: IssueFilter) -> Issues:
        return Issues(
            tuple(
                tracked.issue
                for tracked in self._issues.values()
                if wanted.matches(tracked.creator, tracked.created_on).root
            )
        )

    def read(self, issue: IssueIdentifier) -> Issue:
        return self._tracked(issue).issue

    def add_label(self, issue: IssueIdentifier, label: LabelName) -> None:
        self.set_labels(issue, LabelNames((*self.read(issue).labels.root, label)))

    def set_labels(self, issue: IssueIdentifier, labels: LabelNames) -> None:
        unknown = self._labels.unmatched(labels)
        if len(unknown.root) > 0:
            raise IssueTrackerError(
                f"No label is named {', '.join(label.root for label in unknown.root)}."
            )
        tracked = self._tracked(issue)
        spelled = self._labels.spelled(labels)
        self._issues[issue] = tracked.model_copy(
            update={"issue": tracked.issue.model_copy(update={"labels": spelled})}
        )

    def assign(self, issue: IssueIdentifier, assignee: Assignee) -> None:  # noqa: ARG002
        _ = self._tracked(issue)

    def _tracked(self, issue: IssueIdentifier) -> TrackedIssue:
        tracked = self._issues.get(issue)
        if tracked is None:
            raise IssueTrackerError(f"No issue is identified as {issue.root}.")
        return tracked
