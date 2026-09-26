from typing import Protocol, override

from mb_workflow.b_core.d_domain_model.issue import (
    Assigned,
    Assignee,
    CreatedOn,
    Creator,
    Issue,
    IssueDescription,
    IssueDetail,
    IssueFilter,
    IssueIdentifier,
    Issues,
    IssueTitle,
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

    def read_issue_detail(self, issue: IssueIdentifier) -> IssueDetail: ...

    def add_label(self, issue: IssueIdentifier, label: LabelName) -> None: ...

    def set_labels(self, issue: IssueIdentifier, labels: LabelNames) -> None: ...

    def assign(self, issue: IssueIdentifier, assignee: Assignee) -> None: ...


class TrackedIssue(Model):
    issue: Issue
    title: IssueTitle
    description: IssueDescription | None
    creator: Creator
    created_on: CreatedOn

    @staticmethod
    def fake() -> TrackedIssue:
        return TrackedIssue(
            issue=Issue.fake(),
            title=IssueTitle.fake(),
            description=IssueDescription.fake(),
            creator=Creator.fake(),
            created_on=CreatedOn.fake(),
        )


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
    def read_issue_detail(self, issue: IssueIdentifier) -> IssueDetail:
        tracked = self._tracked(issue)
        return IssueDetail(
            issue=tracked.issue, title=tracked.title, description=tracked.description
        )

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
            update={"issue": tracked.issue.model_copy(update={"assigned": Assigned(True)})}
        )

    def _tracked(self, issue: IssueIdentifier) -> TrackedIssue:
        tracked = self._issues.get(issue)
        if tracked is None:
            raise IssueTrackerError(f"No issue is identified as {issue.root}.")
        return tracked
