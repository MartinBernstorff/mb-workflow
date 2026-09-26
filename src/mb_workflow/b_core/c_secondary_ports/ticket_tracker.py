from typing import Protocol, override

from mb_workflow.b_core.d_domain_model.issue import (
    Assigned,
    Assignee,
    Cleared,
    CreatedOn,
    Creator,
    Issue,
    IssueDescription,
    IssueDetail,
    IssueFilter,
    IssueIdentifier,
    Issues,
    IssueStatusName,
    IssueTitle,
    IssueUpdate,
    LabelName,
    LabelNames,
    Milestone,
    MilestoneName,
    Project,
    ProjectName,
    Projects,
    StatusNames,
)
from mb_workflow.d_lib.models import Model


class TicketTrackerError(Exception):
    pass


class TicketTracker(Protocol):
    def workspace_labels(self) -> LabelNames: ...

    def list_issues(self, wanted: IssueFilter) -> Issues: ...

    def read_issue(self, issue: IssueIdentifier) -> Issue: ...

    def read_issue_detail(self, issue: IssueIdentifier) -> IssueDetail: ...

    def add_label(self, issue: IssueIdentifier, label: LabelName) -> None: ...

    def remove_label(self, issue: IssueIdentifier, label: LabelName) -> None: ...

    def set_labels(self, issue: IssueIdentifier, labels: LabelNames) -> None: ...

    def assign(self, issue: IssueIdentifier, assignee: Assignee) -> None: ...

    def update_issue(self, issue: IssueIdentifier, update: IssueUpdate) -> None: ...

    def viewer(self) -> Assignee: ...


class TrackedIssue(Model):
    issue: Issue
    title: IssueTitle
    description: IssueDescription | None
    assignee: Assignee | None
    milestone: MilestoneName | None
    creator: Creator
    created_on: CreatedOn

    @staticmethod
    def fake() -> TrackedIssue:
        return TrackedIssue(
            issue=Issue.fake(),
            title=IssueTitle.fake(),
            description=IssueDescription.fake(),
            assignee=None,
            milestone=MilestoneName.fake(),
            creator=Creator.fake(),
            created_on=CreatedOn.fake(),
        )


class FakeTicketTracker(TicketTracker):
    def __init__(
        self,
        labels: LabelNames,
        issues: tuple[TrackedIssue, ...],
        projects: Projects = Projects.fake(),
        statuses: StatusNames = StatusNames.fake(),
        viewer: Assignee = Assignee.fake(),
    ) -> None:
        self._labels = labels
        self._issues = {tracked.issue.identifier: tracked for tracked in issues}
        self._projects = projects
        self._statuses = statuses
        self._viewer = viewer

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
            issue=tracked.issue,
            title=tracked.title,
            description=tracked.description,
            assignee=tracked.assignee,
            milestone=tracked.milestone,
        )

    @override
    def add_label(self, issue: IssueIdentifier, label: LabelName) -> None:
        self.set_labels(issue, LabelNames((*self.read_issue(issue).labels.root, label)))

    @override
    def remove_label(self, issue: IssueIdentifier, label: LabelName) -> None:
        (known,) = self._spelled(LabelNames((label,))).root
        self.set_labels(issue, self.read_issue(issue).labels.without(known))

    @override
    def set_labels(self, issue: IssueIdentifier, labels: LabelNames) -> None:
        spelled = self._spelled(labels)
        tracked = self._tracked(issue)
        self._issues[issue] = tracked.model_copy(
            update={"issue": tracked.issue.model_copy(update={"labels": spelled})}
        )

    @override
    def assign(self, issue: IssueIdentifier, assignee: Assignee) -> None:
        tracked = self._tracked(issue)
        self._issues[issue] = tracked.model_copy(
            update={
                "issue": tracked.issue.model_copy(update={"assigned": Assigned(True)}),
                "assignee": assignee,
            }
        )

    @override
    def update_issue(self, issue: IssueIdentifier, update: IssueUpdate) -> None:
        tracked = self._tracked(issue)
        labels = tracked.issue.labels if update.labels is None else self._spelled(update.labels)
        project = self._moved(tracked.issue.project, update.project)
        status = tracked.issue.status if update.status is None else self._status(update.status)
        milestone = self._pinned(
            None if update.project is not None else tracked.milestone, update.milestone
        )
        assignee = tracked.assignee if update.assignee is None else update.assignee
        held = assignee if isinstance(assignee, Assignee) else None
        self._issues[issue] = tracked.model_copy(
            update={
                "issue": tracked.issue.model_copy(
                    update={
                        "labels": labels,
                        "project": project,
                        "status": status,
                        "assigned": Assigned(held is not None),
                    }
                ),
                "title": tracked.title if update.title is None else update.title,
                "description": (
                    tracked.description if update.description is None else update.description
                ),
                "assignee": held,
                "milestone": milestone,
            }
        )

    @override
    def viewer(self) -> Assignee:
        return self._viewer

    def _spelled(self, labels: LabelNames) -> LabelNames:
        unknown = self._labels.unmatched(labels)
        if len(unknown.root) > 0:
            raise TicketTrackerError(
                f"No label is named {', '.join(label.root for label in unknown.root)}."
            )
        return self._labels.spelled(labels)

    def _moved(
        self, held: ProjectName | None, wanted: ProjectName | Cleared | None
    ) -> ProjectName | None:
        if wanted is None:
            return held
        if isinstance(wanted, Cleared):
            return None
        return self._project(wanted).name

    def _pinned(
        self, held: MilestoneName | None, wanted: Milestone | Cleared | None
    ) -> MilestoneName | None:
        if wanted is None:
            return held
        if isinstance(wanted, Cleared):
            return None
        found = self._project(wanted.project).milestones.matching(wanted.name)
        if found is None:
            raise TicketTrackerError(
                f"{wanted.project.root} has no milestone named {wanted.name.root}."
            )
        return found

    def _status(self, name: IssueStatusName) -> IssueStatusName:
        status = self._statuses.matching(name)
        if status is None:
            raise TicketTrackerError(f"No status is named {name.root}.")
        return status

    def _project(self, name: ProjectName) -> Project:
        project = self._projects.matching(name)
        if project is None:
            raise TicketTrackerError(f"No project is named {name.root}.")
        return project

    def _tracked(self, issue: IssueIdentifier) -> TrackedIssue:
        tracked = self._issues.get(issue)
        if tracked is None:
            raise TicketTrackerError(f"No issue is identified as {issue.root}.")
        return tracked
