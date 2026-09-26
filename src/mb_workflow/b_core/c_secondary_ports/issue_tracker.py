from typing import Protocol, override

from mb_workflow.b_core.d_domain_model.issue import (
    Assignee,
    Clear,
    CreatedOn,
    Creator,
    Issue,
    IssueEdit,
    IssueFilter,
    IssueIdentifier,
    Issues,
    IssueUrl,
    LabelName,
    LabelNames,
)
from mb_workflow.d_lib.models import Model


class IssueTrackerError(Exception):
    pass


class IssueTracker(Protocol):
    def workspace_labels(self) -> LabelNames: ...

    def list_issues(self, wanted: IssueFilter) -> Issues: ...

    def read_issue(self, issue: IssueIdentifier) -> Issue: ...

    def add_label(self, issue: IssueIdentifier, label: LabelName) -> None: ...

    def set_labels(self, issue: IssueIdentifier, labels: LabelNames) -> None: ...

    def assign(self, issue: IssueIdentifier, assignee: Assignee) -> None: ...

    def viewer(self) -> Assignee: ...

    def edit(self, issue: IssueIdentifier, change: IssueEdit) -> IssueUrl: ...


class TrackedIssue(Model):
    issue: Issue
    creator: Creator
    created_on: CreatedOn

    @staticmethod
    def fake() -> TrackedIssue:
        return TrackedIssue(issue=Issue.fake(), creator=Creator.fake(), created_on=CreatedOn.fake())


class FakeIssueTracker(IssueTracker):
    def __init__(self, labels: LabelNames, issues: tuple[TrackedIssue, ...]) -> None:
        self._labels = labels
        self._issues = {tracked.issue.identifier: tracked for tracked in issues}

    @override
    def workspace_labels(self) -> LabelNames:
        return self._labels

    @override
    def list_issues(self, wanted: IssueFilter) -> Issues:
        return Issues(
            tuple(
                tracked.issue
                for tracked in self._issues.values()
                if wanted.matches(tracked.creator, tracked.created_on).root
            )
        )

    @override
    def read_issue(self, issue: IssueIdentifier) -> Issue:
        return self._tracked(issue).issue

    @override
    def add_label(self, issue: IssueIdentifier, label: LabelName) -> None:
        self.set_labels(issue, LabelNames((*self.read_issue(issue).labels.root, label)))

    @override
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

    @override
    def assign(self, issue: IssueIdentifier, assignee: Assignee) -> None:
        tracked = self._tracked(issue)
        self._issues[issue] = tracked.model_copy(
            update={"issue": tracked.issue.model_copy(update={"assignee": assignee})}
        )

    @override
    def viewer(self) -> Assignee:
        return Assignee.fake()

    @override
    def edit(self, issue: IssueIdentifier, change: IssueEdit) -> IssueUrl:
        current = self.read_issue(issue)
        unknown = self._labels.unmatched(change.removed_labels)
        if len(unknown.root) > 0:
            raise IssueTrackerError(
                f"No label is named {', '.join(label.root for label in unknown.root)}."
            )
        removed = self._labels.spelled(change.removed_labels)
        kept = LabelNames(
            tuple(label for label in current.labels.root if label not in removed.root)
        )
        self.set_labels(issue, LabelNames((*kept.root, *change.added_labels.root)))
        tracked = self._tracked(issue)
        edited = tracked.issue.model_copy(
            update={
                "title": cleared(change.title, tracked.issue.title),
                "body": cleared(change.body, tracked.issue.body),
                "assignee": cleared(change.assignee, tracked.issue.assignee),
                "project": cleared(change.project, tracked.issue.project),
                "milestone": cleared(change.milestone, tracked.issue.milestone),
            }
        )
        self._issues[issue] = tracked.model_copy(update={"issue": edited})
        return IssueUrl(f"https://linear.app/fake/issue/{issue.root}")

    def _tracked(self, issue: IssueIdentifier) -> TrackedIssue:
        tracked = self._issues.get(issue)
        if tracked is None:
            raise IssueTrackerError(f"No issue is identified as {issue.root}.")
        return tracked


def cleared[T](change: T | Clear | None, current: T | None) -> T | None:
    if change is None:
        return current
    if isinstance(change, Clear):
        return None
    return change
