from itertools import count
from typing import TYPE_CHECKING, Protocol, override

from mb_workflow.b_core.d_domain_model.claim import Released
from mb_workflow.b_core.d_domain_model.issue import (
    Assigned,
    Assignee,
    Cleared,
    CreatedIssue,
    CreatedOn,
    Creator,
    GroupedLabel,
    GroupedLabels,
    Issue,
    IssueDescription,
    IssueDetail,
    IssueFilter,
    IssueIdentifier,
    Issues,
    IssueStatus,
    IssueStatuses,
    IssueStatusName,
    IssueTitle,
    IssueUpdate,
    IssueUrl,
    LabelName,
    LabelNames,
    Milestone,
    MilestoneName,
    NewIssue,
    Project,
    ProjectName,
    Projects,
    StatusNames,
    StatusTypes,
    Team,
    TeamKey,
)
from mb_workflow.b_core.d_domain_model.pool import PoolTicket, PoolTickets, Priority, ViewSlug
from mb_workflow.d_lib.models import Model

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.issue import LabelGroupName


class TicketTrackerError(Exception):
    pass


class TicketTracker(Protocol):
    def workspace_labels(self) -> LabelNames: ...

    def group_labels(self, group: LabelGroupName) -> LabelNames: ...

    def create_group_labels(self, group: LabelGroupName, labels: LabelNames) -> None: ...

    def list_issues(self, wanted: IssueFilter) -> Issues: ...

    def unblocked_view_tickets(self, view: ViewSlug) -> PoolTickets: ...

    def labelled_issues(self, label: LabelName, excluding: StatusTypes) -> Issues: ...

    def read_issue(self, issue: IssueIdentifier) -> Issue: ...

    def read_issue_detail(self, issue: IssueIdentifier) -> IssueDetail: ...

    def add_label(self, issue: IssueIdentifier, label: LabelName) -> None: ...

    def remove_label(self, issue: IssueIdentifier, label: LabelName) -> None: ...

    def set_labels(self, issue: IssueIdentifier, labels: LabelNames) -> None: ...

    def assign(self, issue: IssueIdentifier, assignee: Assignee) -> None: ...

    def update_issue(self, issue: IssueIdentifier, update: IssueUpdate) -> None: ...

    def create_issue(self, new: NewIssue) -> CreatedIssue: ...

    def blockers(self, issue: IssueIdentifier) -> tuple[IssueIdentifier, ...]: ...

    def viewer(self) -> Assignee: ...


class TrackedIssue(Model):
    issue: Issue
    title: IssueTitle
    description: IssueDescription | None
    assignee: Assignee | None
    milestone: MilestoneName | None
    creator: Creator
    created_on: CreatedOn
    priority: Priority
    blocked_by: tuple[IssueIdentifier, ...]

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
            priority=Priority.medium,
            blocked_by=(),
        )


class FakeTicketTracker(TicketTracker):
    def __init__(
        self,
        labels: LabelNames,
        issues: tuple[TrackedIssue, ...],
        projects: Projects = Projects.fake(),
        statuses: IssueStatuses = IssueStatuses.fake(),
        viewer: Assignee = Assignee.fake(),
        *,
        views: dict[ViewSlug, tuple[IssueIdentifier, ...]] | None = None,
        groups: dict[LabelGroupName, LabelNames] | None = None,
        teams: tuple[Team, ...] = (Team.fake(),),
    ) -> None:
        self._labels = labels
        self._issues = {tracked.issue.identifier: tracked for tracked in issues}
        self._projects = projects
        self._statuses = statuses
        self._viewer = viewer
        self._views = dict(views or {})
        self._groups = dict(groups or {})
        self._teams = teams

    @override
    def workspace_labels(self) -> LabelNames:
        return self._labels

    @override
    def group_labels(self, group: LabelGroupName) -> LabelNames:
        return self._groups.get(group, LabelNames(()))

    @override
    def create_group_labels(self, group: LabelGroupName, labels: LabelNames) -> None:
        self._groups[group] = LabelNames((*self.group_labels(group).root, *labels.root))
        self._labels = LabelNames((*self._labels.root, *labels.root))

    @override
    def list_issues(self, wanted: IssueFilter) -> Issues:
        return Issues(
            tuple(
                self._read(tracked)
                for tracked in self._issues.values()
                if wanted.matches(tracked.creator, tracked.created_on).root
            )
        )

    @override
    def unblocked_view_tickets(self, view: ViewSlug) -> PoolTickets:
        listed = self._views.get(view)
        if listed is None:
            raise TicketTrackerError(f"No view has the slug {view.root}.")
        return PoolTickets(
            tuple(
                PoolTicket(issue=self._read(tracked), priority=tracked.priority)
                for tracked in (self._tracked(identifier) for identifier in listed)
                if not self._open_blockers(tracked)
            )
        )

    @override
    def labelled_issues(self, label: LabelName, excluding: StatusTypes) -> Issues:
        return Issues(
            tuple(
                self._read(tracked)
                for tracked in self._issues.values()
                if tracked.issue.labels.matching(label) is not None
                and not excluding.has(self._status_named(tracked.issue.status).type).root
            )
        )

    @override
    def read_issue(self, issue: IssueIdentifier) -> Issue:
        return self._read(self._tracked(issue))

    @override
    def read_issue_detail(self, issue: IssueIdentifier) -> IssueDetail:
        tracked = self._tracked(issue)
        return IssueDetail(
            issue=self._read(tracked),
            title=tracked.title,
            description=tracked.description,
            assignee=tracked.assignee,
            milestone=tracked.milestone,
            blocks=frozenset(
                identifier
                for identifier, other in self._issues.items()
                if issue in other.blocked_by
            ),
            blocked_by=frozenset(tracked.blocked_by),
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
        status = (
            tracked.issue.status
            if update.status is None
            else self._status_named(update.status).name
        )
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
    def create_issue(self, new: NewIssue) -> CreatedIssue:
        _ = self._team(new.team, new.project)
        for blocker in new.blocked_by:
            _ = self._tracked(blocker)
        blocked = tuple(self._tracked(issue) for issue in new.blocks)
        identifier = next(
            candidate
            for candidate in (IssueIdentifier(f"E-{n}") for n in count(len(self._issues) + 1))
            if candidate not in self._issues
        )
        self._issues[identifier] = TrackedIssue(
            issue=Issue(
                identifier=identifier,
                status=self._status_named(new.status).name,
                project=self._moved(None, new.project),
                labels=self._spelled(new.labels),
                grouped=GroupedLabels(()),
                assigned=Assigned(new.assignee is not None),
            ),
            title=new.title,
            description=new.description,
            assignee=new.assignee,
            milestone=self._pinned(None, new.milestone),
            creator=Creator(self._viewer.root),
            created_on=CreatedOn.fake(),
            priority=Priority.no_priority,
            blocked_by=new.blocked_by,
        )
        for tracked in blocked:
            self._issues[tracked.issue.identifier] = tracked.model_copy(
                update={"blocked_by": (*tracked.blocked_by, identifier)}
            )
        return CreatedIssue(
            identifier=identifier, url=IssueUrl(f"https://linear.app/fake/issue/{identifier.root}")
        )

    @override
    def blockers(self, issue: IssueIdentifier) -> tuple[IssueIdentifier, ...]:
        return self._tracked(issue).blocked_by

    @override
    def viewer(self) -> Assignee:
        return self._viewer

    def _team(self, key: TeamKey | None, project: ProjectName | None) -> Team:
        if key is not None:
            found = next((team for team in self._teams if team.key.names(key).root), None)
            if found is None:
                raise TicketTrackerError(f"No team has the key {key.root}.")
            return found
        if project is None:
            raise TicketTrackerError("Name a team or a project to create the issue in.")
        spelled = self._project(project).name
        owners = tuple(team for team in self._teams if spelled in team.projects)
        if len(owners) != 1:
            raise TicketTrackerError(
                f"{spelled.root} belongs to several teams. Set [issues] team to pick one."
            )
        return owners[0]

    def _spelled(self, labels: LabelNames) -> LabelNames:
        unknown = self._labels.unmatched(labels)
        if len(unknown.root) > 0:
            raise TicketTrackerError(
                f"No label is named {', '.join(label.root for label in unknown.root)}."
            )
        spelled = self._labels.spelled(labels)
        for group, members in self._groups.items():
            held = members.spelled(spelled)
            if len(held.root) > 1:
                raise TicketTrackerError(
                    f"{', '.join(label.root for label in held.root)} are all in the"
                    f" {group.root} group, and an issue carries at most one label of a group."
                )
        return spelled

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

    def _status_named(self, name: IssueStatusName) -> IssueStatus:
        status = self._statuses.matching(name)
        if status is None:
            raise TicketTrackerError(f"No status is named {name.root}.")
        return status

    def _project(self, name: ProjectName) -> Project:
        project = self._projects.matching(name)
        if project is None:
            raise TicketTrackerError(f"No project is named {name.root}.")
        return project

    # Linear counts a blocker as open until it reaches a completed or canceled state.
    def _open_blockers(self, tracked: TrackedIssue) -> tuple[IssueIdentifier, ...]:
        finished = StatusNames((*Released.statuses().root, IssueStatusName("Done")))
        return tuple(
            blocker
            for blocker in tracked.blocked_by
            if finished.matching(self._tracked(blocker).issue.status) is None
        )

    # Linear reports each label's group on the issue, so the fake reads it from the groups it keeps.
    def _read(self, tracked: TrackedIssue) -> Issue:
        grouped = GroupedLabels(
            tuple(
                GroupedLabel(group=group, label=label)
                for label in tracked.issue.labels.root
                for group, members in self._groups.items()
                if members.matching(label) is not None
            )
        )
        return tracked.issue.model_copy(update={"grouped": grouped})

    def _tracked(self, issue: IssueIdentifier) -> TrackedIssue:
        tracked = self._issues.get(issue)
        if tracked is None:
            raise TicketTrackerError(f"No issue is identified as {issue.root}.")
        return tracked
