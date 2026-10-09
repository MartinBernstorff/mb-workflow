import logging
from itertools import count
from typing import TYPE_CHECKING, Protocol, override

from safe_result import Err, Ok, Result

from mb_workflow.b_core.d_domain_model.claim import Released
from mb_workflow.b_core.d_domain_model.issue import (
    Assigned,
    Assignee,
    Cleared,
    ColoredLabel,
    ColoredLabels,
    CreatedIssue,
    CreatedOn,
    Creator,
    Estimate,
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
    LabelColor,
    LabelName,
    LabelNames,
    Milestone,
    MilestoneName,
    NewIssue,
    Priority,
    Project,
    ProjectName,
    Projects,
    StatusNames,
    StatusTypes,
    Team,
    TeamKey,
    TeamName,
    TicketCount,
    UpdatedAt,
)
from mb_workflow.b_core.d_domain_model.pool import PoolTicket, PoolTickets, ViewSlug
from mb_workflow.d_lib.logging import Activity
from mb_workflow.d_lib.models import Model

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.issue import LabelGroupName


logger = logging.getLogger(__name__)


class TicketTrackerError(Exception):
    pass


class TicketTracker(Protocol):
    def workspace_labels(self) -> Result[LabelNames, TicketTrackerError]: ...

    # A team of None reads or creates the group at workspace level, outside every team.
    def group_labels(
        self, group: LabelGroupName, team: TeamKey | None
    ) -> Result[ColoredLabels, TicketTrackerError]: ...

    def label_group(
        self, label: LabelName
    ) -> Result[LabelGroupName | None, TicketTrackerError]: ...

    def create_group_labels(
        self, group: LabelGroupName, labels: ColoredLabels, team: TeamKey | None
    ) -> Result[None, TicketTrackerError]: ...

    def recolor_group_labels(
        self, group: LabelGroupName, labels: ColoredLabels, team: TeamKey | None
    ) -> Result[None, TicketTrackerError]: ...

    def rename_group_label(
        self, group: LabelGroupName, label: LabelName, renamed: LabelName, team: TeamKey | None
    ) -> Result[None, TicketTrackerError]: ...

    # Deleting a label also takes it off every ticket that carries it.
    def delete_group_label(
        self, group: LabelGroupName, label: LabelName, team: TeamKey | None
    ) -> Result[None, TicketTrackerError]: ...

    def labelled_ticket_count(
        self, group: LabelGroupName, label: LabelName, team: TeamKey | None
    ) -> Result[TicketCount, TicketTrackerError]: ...

    def team_named(self, name: TeamName) -> Result[TeamKey, TicketTrackerError]: ...

    def team_of(self, issue: IssueIdentifier) -> Result[TeamKey, TicketTrackerError]: ...

    def list_issues(self, wanted: IssueFilter) -> Result[Issues, TicketTrackerError]: ...

    def unblocked_view_tickets(self, view: ViewSlug) -> Result[PoolTickets, TicketTrackerError]: ...

    def labelled_issues(
        self, label: LabelName, excluding: StatusTypes
    ) -> Result[Issues, TicketTrackerError]: ...

    def read_issue(self, issue: IssueIdentifier) -> Result[Issue, TicketTrackerError]: ...

    def read_issue_detail(
        self, issue: IssueIdentifier
    ) -> Result[IssueDetail, TicketTrackerError]: ...

    def add_label(
        self, issue: IssueIdentifier, label: LabelName
    ) -> Result[None, TicketTrackerError]: ...

    def remove_label(
        self, issue: IssueIdentifier, label: LabelName
    ) -> Result[None, TicketTrackerError]: ...

    def set_labels(
        self, issue: IssueIdentifier, labels: LabelNames
    ) -> Result[None, TicketTrackerError]: ...

    def assign(
        self, issue: IssueIdentifier, assignee: Assignee
    ) -> Result[None, TicketTrackerError]: ...

    def update_issue(
        self, issue: IssueIdentifier, update: IssueUpdate
    ) -> Result[None, TicketTrackerError]: ...

    def create_issue(self, new: NewIssue) -> Result[CreatedIssue, TicketTrackerError]: ...

    def blockers(
        self, issue: IssueIdentifier
    ) -> Result[tuple[IssueIdentifier, ...], TicketTrackerError]: ...

    def viewer(self) -> Result[Assignee, TicketTrackerError]: ...


class LabelCheck:
    @staticmethod
    def require_label[E: Exception](
        tracker: TicketTracker, label: LabelName, missing: E
    ) -> Result[None, TicketTrackerError | E]:
        with Activity(f"Checking that label {label.root} exists").logged(logger):
            listed = tracker.workspace_labels()
        match listed:
            case Ok(known):
                if known.matching(label) is None:
                    return Err(missing)
                return Ok(None)
            case Err() as failed:
                return failed


class TrackedIssue(Model):
    issue: Issue
    title: IssueTitle
    description: IssueDescription | None
    assignee: Assignee | None
    milestone: MilestoneName | None
    creator: Creator
    created_on: CreatedOn
    updated_at: UpdatedAt
    priority: Priority
    estimate: Estimate | None
    blocked_by: tuple[IssueIdentifier, ...]
    parent: IssueIdentifier | None
    related: tuple[IssueIdentifier, ...]
    team: TeamKey

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
            updated_at=UpdatedAt.fake(),
            priority=Priority.medium,
            estimate=None,
            blocked_by=(),
            parent=None,
            related=(),
            team=TeamKey.fake(),
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
        team_groups: dict[tuple[TeamKey, LabelGroupName], LabelNames] | None = None,
        teams: tuple[Team, ...] = (Team.fake(),),
    ) -> None:
        self._labels = labels
        self._issues = {tracked.issue.identifier: tracked for tracked in issues}
        self._clock = UpdatedAt(
            max((tracked.updated_at.root for tracked in issues), default=UpdatedAt.fake().root)
        )
        self._projects = projects
        self._statuses = statuses
        self._viewer = viewer
        self._views = dict(views or {})
        self._groups = {
            group: FakeTicketTracker._uncolored(labels) for group, labels in (groups or {}).items()
        }
        self._team_groups = {
            key: FakeTicketTracker._uncolored(labels) for key, labels in (team_groups or {}).items()
        }
        self._teams = teams

    # Linear lists every label, a team's own ones included.
    @override
    def workspace_labels(self) -> Result[LabelNames, TicketTrackerError]:
        return Ok(
            LabelNames(
                (
                    *self._labels.root,
                    *(
                        label
                        for held in self._team_groups.values()
                        for label in held.label_names().root
                    ),
                )
            )
        )

    @override
    def group_labels(
        self, group: LabelGroupName, team: TeamKey | None
    ) -> Result[ColoredLabels, TicketTrackerError]:
        return Ok(self._group_members(group, team))

    @override
    def label_group(self, label: LabelName) -> Result[LabelGroupName | None, TicketTrackerError]:
        return Ok(
            next(
                (
                    group
                    for group, members in (
                        *self._groups.items(),
                        *((group, members) for (_, group), members in self._team_groups.items()),
                    )
                    if members.label_names().matching(label) is not None
                ),
                None,
            )
        )

    @override
    def create_group_labels(
        self, group: LabelGroupName, labels: ColoredLabels, team: TeamKey | None
    ) -> Result[None, TicketTrackerError]:
        held = ColoredLabels((*self._group_members(group, team).root, *labels.root))
        if team is None:
            self._groups[group] = held
            self._labels = LabelNames((*self._labels.root, *labels.label_names().root))
        else:
            self._team_groups[(team, group)] = held
        return Ok(None)

    @override
    def recolor_group_labels(
        self, group: LabelGroupName, labels: ColoredLabels, team: TeamKey | None
    ) -> Result[None, TicketTrackerError]:
        held = self._group_members(group, team)
        unknown = held.label_names().unmatched(labels.label_names())
        if unknown.root:
            return Err(
                TicketTrackerError(
                    f"The {group.root} group holds no label named"
                    f" {', '.join(label.root for label in unknown.root)}."
                )
            )
        colors = {label.name.root.casefold(): label.color for label in labels.root}
        recolored = ColoredLabels(
            tuple(
                ColoredLabel(
                    name=label.name, color=colors.get(label.name.root.casefold(), label.color)
                )
                for label in held.root
            )
        )
        self._store_group(group, team, recolored)
        return Ok(None)

    @override
    def rename_group_label(
        self, group: LabelGroupName, label: LabelName, renamed: LabelName, team: TeamKey | None
    ) -> Result[None, TicketTrackerError]:
        match self._group_member(group, label, team):
            case Ok(known):
                held = self._group_members(group, team)
                self._store_group(
                    group,
                    team,
                    ColoredLabels(
                        tuple(
                            member.model_copy(update={"name": renamed})
                            if member.name == known
                            else member
                            for member in held.root
                        )
                    ),
                )
                if team is None:
                    self._labels = self._labels.replaced(known, renamed)
                for tracked in self._carrying(known, team):
                    self._relabel(tracked, tracked.issue.labels.replaced(known, renamed))
                return Ok(None)
            case Err() as failed:
                return failed

    @override
    def delete_group_label(
        self, group: LabelGroupName, label: LabelName, team: TeamKey | None
    ) -> Result[None, TicketTrackerError]:
        match self._group_member(group, label, team):
            case Ok(known):
                held = self._group_members(group, team)
                self._store_group(
                    group,
                    team,
                    ColoredLabels(tuple(member for member in held.root if member.name != known)),
                )
                if team is None:
                    self._labels = self._labels.without(known)
                for tracked in self._carrying(known, team):
                    self._relabel(tracked, tracked.issue.labels.without(known))
                return Ok(None)
            case Err() as failed:
                return failed

    @override
    def labelled_ticket_count(
        self, group: LabelGroupName, label: LabelName, team: TeamKey | None
    ) -> Result[TicketCount, TicketTrackerError]:
        match self._group_member(group, label, team):
            case Ok(known):
                return Ok(TicketCount(len(self._carrying(known, team))))
            case Err() as failed:
                return failed

    @override
    def team_named(self, name: TeamName) -> Result[TeamKey, TicketTrackerError]:
        found = next((team for team in self._teams if team.name.names(name).root), None)
        if found is None:
            return Err(TicketTrackerError(f"No team is named {name.root}."))
        return Ok(found.key)

    @override
    def team_of(self, issue: IssueIdentifier) -> Result[TeamKey, TicketTrackerError]:
        match self._found(issue):
            case Ok(tracked):
                return Ok(tracked.team)
            case Err() as failed:
                return failed

    @override
    def list_issues(self, wanted: IssueFilter) -> Result[Issues, TicketTrackerError]:
        return Ok(
            Issues(
                tuple(
                    self._read(tracked)
                    for tracked in self._issues.values()
                    if wanted.matches(tracked.creator, tracked.created_on).root
                )
            )
        )

    @override
    def unblocked_view_tickets(self, view: ViewSlug) -> Result[PoolTickets, TicketTrackerError]:
        listed = self._views.get(view)
        if listed is None:
            return Err(TicketTrackerError(f"No view has the slug {view.root}."))
        unblocked: list[PoolTicket] = []
        for identifier in listed:
            found = self._found(identifier)
            if isinstance(found, Err):
                return found
            blockers = self._open_blockers(found.value)
            if isinstance(blockers, Err):
                return blockers
            if not blockers.value:
                unblocked.append(
                    PoolTicket(
                        issue=self._read(found.value),
                        priority=found.value.priority,
                        updated_at=found.value.updated_at,
                    )
                )
        return Ok(PoolTickets(tuple(unblocked)))

    @override
    def labelled_issues(
        self, label: LabelName, excluding: StatusTypes
    ) -> Result[Issues, TicketTrackerError]:
        labelled: list[Issue] = []
        for tracked in self._issues.values():
            if tracked.issue.labels.matching(label) is None:
                continue
            status = self._status_named(tracked.issue.status)
            if isinstance(status, Err):
                return status
            if not excluding.has(status.value.type).root:
                labelled.append(self._read(tracked))
        return Ok(Issues(tuple(labelled)))

    @override
    def read_issue(self, issue: IssueIdentifier) -> Result[Issue, TicketTrackerError]:
        match self._found(issue):
            case Ok(value):
                return Ok(self._read(value))
            case Err() as failed:
                return failed

    @override
    def read_issue_detail(self, issue: IssueIdentifier) -> Result[IssueDetail, TicketTrackerError]:
        match self._found(issue):
            case Ok(tracked):
                return Ok(
                    IssueDetail(
                        issue=self._read(tracked),
                        title=tracked.title,
                        description=tracked.description,
                        assignee=tracked.assignee,
                        milestone=tracked.milestone,
                        priority=tracked.priority,
                        estimate=tracked.estimate,
                        parent=tracked.parent,
                        sub_tickets=frozenset(
                            identifier
                            for identifier, other in self._issues.items()
                            if other.parent == issue
                        ),
                        blocks=frozenset(
                            identifier
                            for identifier, other in self._issues.items()
                            if issue in other.blocked_by
                        ),
                        blocked_by=frozenset(tracked.blocked_by),
                        related=frozenset(
                            (
                                *tracked.related,
                                *(
                                    identifier
                                    for identifier, other in self._issues.items()
                                    if issue in other.related
                                ),
                            )
                        ),
                    )
                )
            case Err() as failed:
                return failed

    @override
    def add_label(
        self, issue: IssueIdentifier, label: LabelName
    ) -> Result[None, TicketTrackerError]:
        match self._found(issue):
            case Ok(tracked):
                return self.set_labels(issue, LabelNames((*tracked.issue.labels.root, label)))
            case Err() as failed:
                return failed

    @override
    def remove_label(
        self, issue: IssueIdentifier, label: LabelName
    ) -> Result[None, TicketTrackerError]:
        found = self._found(issue)
        if isinstance(found, Err):
            return found
        spelled = self._spelled(LabelNames((label,)), found.value.team)
        if isinstance(spelled, Err):
            return spelled
        (known,) = spelled.value.root
        return self.set_labels(issue, found.value.issue.labels.without(known))

    @override
    def set_labels(
        self, issue: IssueIdentifier, labels: LabelNames
    ) -> Result[None, TicketTrackerError]:
        found = self._found(issue)
        if isinstance(found, Err):
            return found
        spelled = self._spelled(labels, found.value.team)
        if isinstance(spelled, Err):
            return spelled
        self._relabel(found.value, spelled.value)
        return Ok(None)

    @override
    def assign(
        self, issue: IssueIdentifier, assignee: Assignee
    ) -> Result[None, TicketTrackerError]:
        match self._found(issue):
            case Ok(tracked):
                self._issues[issue] = self._stamped_with_next_update(
                    tracked.model_copy(
                        update={
                            "issue": tracked.issue.model_copy(update={"assigned": Assigned(True)}),
                            "assignee": assignee,
                        }
                    )
                )
                return Ok(None)
            case Err() as failed:
                return failed

    @override
    def update_issue(
        self, issue: IssueIdentifier, update: IssueUpdate
    ) -> Result[None, TicketTrackerError]:
        found = self._found(issue)
        if isinstance(found, Err):
            return found
        updated = self._updated(found.value, update)
        if isinstance(updated, Err):
            return updated
        related = self._all_found((*update.blocks, *update.blocked_by))
        if isinstance(related, Err):
            return related
        self._issues[issue] = self._stamped_with_next_update(updated.value)
        for blocked in update.blocks:
            other = self._issues[blocked]
            self._issues[blocked] = self._stamped_with_next_update(
                other.model_copy(update={"blocked_by": (*other.blocked_by, issue)})
            )
        return Ok(None)

    @override
    def create_issue(self, new: NewIssue) -> Result[CreatedIssue, TicketTrackerError]:
        identifier = next(
            candidate
            for candidate in (IssueIdentifier(f"E-{n}") for n in count(len(self._issues) + 1))
            if candidate not in self._issues
        )
        created = self._created(identifier, new)
        if isinstance(created, Err):
            return created
        related = self._all_found((*new.blocked_by, *new.blocks))
        if isinstance(related, Err):
            return related
        self._issues[identifier] = self._stamped_with_next_update(created.value)
        for blocked in new.blocks:
            other = self._issues[blocked]
            self._issues[blocked] = self._stamped_with_next_update(
                other.model_copy(update={"blocked_by": (*other.blocked_by, identifier)})
            )
        return Ok(
            CreatedIssue(
                identifier=identifier,
                url=IssueUrl(f"https://linear.app/fake/issue/{identifier.root}"),
            )
        )

    @override
    def blockers(
        self, issue: IssueIdentifier
    ) -> Result[tuple[IssueIdentifier, ...], TicketTrackerError]:
        match self._found(issue):
            case Ok(tracked):
                return Ok(tracked.blocked_by)
            case Err() as failed:
                return failed

    @override
    def viewer(self) -> Result[Assignee, TicketTrackerError]:
        return Ok(self._viewer)

    def _group_members(self, group: LabelGroupName, team: TeamKey | None) -> ColoredLabels:
        if team is None:
            return self._groups.get(group, ColoredLabels(()))
        return self._team_groups.get((team, group), ColoredLabels(()))

    def _store_group(
        self, group: LabelGroupName, team: TeamKey | None, members: ColoredLabels
    ) -> None:
        if team is None:
            self._groups[group] = members
        else:
            self._team_groups[(team, group)] = members

    def _group_member(
        self, group: LabelGroupName, label: LabelName, team: TeamKey | None
    ) -> Result[LabelName, TicketTrackerError]:
        known = self._group_members(group, team).label_names().matching(label)
        if known is None:
            return Err(
                TicketTrackerError(f"The {group.root} group holds no label named {label.root}.")
            )
        return Ok(known)

    # A team's label is carried only by that team's tickets; a workspace label by any ticket.
    def _carrying(self, label: LabelName, team: TeamKey | None) -> tuple[TrackedIssue, ...]:
        return tuple(
            tracked
            for tracked in self._issues.values()
            if label in tracked.issue.labels.root
            and (team is None or tracked.team.names(team).root)
        )

    def _relabel(self, tracked: TrackedIssue, labels: LabelNames) -> None:
        self._issues[tracked.issue.identifier] = self._stamped_with_next_update(
            tracked.model_copy(
                update={"issue": tracked.issue.model_copy(update={"labels": labels})}
            )
        )

    # Every write stamps the ticket a moment after the last, as Linear's updatedAt does.
    def _stamped_with_next_update(self, tracked: TrackedIssue) -> TrackedIssue:
        self._clock = self._clock.later()
        return tracked.model_copy(update={"updated_at": self._clock})

    def _updated(
        self, tracked: TrackedIssue, update: IssueUpdate
    ) -> Result[TrackedIssue, TicketTrackerError]:
        labels = (
            Ok(tracked.issue.labels)
            if update.labels is None
            else self._spelled(update.labels, tracked.team)
        )
        if isinstance(labels, Err):
            return labels
        project = self._moved(tracked.issue.project, update.project)
        if isinstance(project, Err):
            return project
        status = None if update.status is None else self._status_named(update.status)
        if isinstance(status, Err):
            return status
        milestone = self._pinned(
            None if update.project is not None else tracked.milestone, update.milestone
        )
        if isinstance(milestone, Err):
            return milestone
        assignee = tracked.assignee if update.assignee is None else update.assignee
        held = assignee if isinstance(assignee, Assignee) else None
        return Ok(
            tracked.model_copy(
                update={
                    "issue": tracked.issue.model_copy(
                        update={
                            "labels": labels.value,
                            "project": project.value,
                            "status": tracked.issue.status if status is None else status.value.name,
                            "assigned": Assigned(held is not None),
                        }
                    ),
                    "title": tracked.title if update.title is None else update.title,
                    "description": (
                        tracked.description if update.description is None else update.description
                    ),
                    "assignee": held,
                    "milestone": milestone.value,
                    "priority": tracked.priority if update.priority is None else update.priority,
                    "estimate": tracked.estimate if update.estimate is None else update.estimate,
                    "blocked_by": (*tracked.blocked_by, *update.blocked_by),
                }
            )
        )

    def _created(
        self, identifier: IssueIdentifier, new: NewIssue
    ) -> Result[TrackedIssue, TicketTrackerError]:
        team = self._team(new.team, new.project)
        if isinstance(team, Err):
            return team
        status = self._status_named(new.status)
        if isinstance(status, Err):
            return status
        project = self._moved(None, new.project)
        if isinstance(project, Err):
            return project
        labels = self._spelled(new.labels, team.value.key)
        if isinstance(labels, Err):
            return labels
        milestone = self._pinned(None, new.milestone)
        if isinstance(milestone, Err):
            return milestone
        return Ok(
            TrackedIssue(
                issue=Issue(
                    identifier=identifier,
                    status=status.value.name,
                    project=project.value,
                    labels=labels.value,
                    grouped=GroupedLabels(()),
                    assigned=Assigned(new.assignee is not None),
                ),
                title=new.title,
                description=new.description,
                assignee=new.assignee,
                milestone=milestone.value,
                creator=Creator(self._viewer.root),
                created_on=CreatedOn.fake(),
                updated_at=self._clock,
                priority=Priority.no_priority if new.priority is None else new.priority,
                estimate=new.estimate,
                blocked_by=new.blocked_by,
                parent=None,
                related=(),
                team=team.value.key,
            )
        )

    def _all_found(self, issues: tuple[IssueIdentifier, ...]) -> Result[None, TicketTrackerError]:
        for issue in issues:
            found = self._found(issue)
            if isinstance(found, Err):
                return found
        return Ok(None)

    def _team(
        self, key: TeamKey | None, project: ProjectName | None
    ) -> Result[Team, TicketTrackerError]:
        if key is not None:
            found = next((team for team in self._teams if team.key.names(key).root), None)
            if found is None:
                return Err(TicketTrackerError(f"No team has the key {key.root}."))
            return Ok(found)
        if project is None:
            return Err(TicketTrackerError("Name a team or a project to create the issue in."))
        known = self._project(project)
        if isinstance(known, Err):
            return known
        spelled = known.value.name
        owners = tuple(team for team in self._teams if spelled in team.projects)
        if len(owners) != 1:
            return Err(
                TicketTrackerError(
                    f"{spelled.root} belongs to several teams. Set [issues] team to pick one."
                )
            )
        return Ok(owners[0])

    # An issue carries only workspace labels and those of its own team.
    def _spelled(self, labels: LabelNames, team: TeamKey) -> Result[LabelNames, TicketTrackerError]:
        groups = self._groups_of(team)
        known = LabelNames(
            (*self._labels.root, *(label for _, members in groups for label in members.root))
        )
        unknown = known.unmatched(labels)
        if len(unknown.root) > 0:
            return Err(
                TicketTrackerError(
                    f"No label is named {', '.join(label.root for label in unknown.root)}."
                )
            )
        spelled = known.spelled(labels)
        for group, members in groups:
            held = members.spelled(spelled)
            if len(held.root) > 1:
                return Err(
                    TicketTrackerError(
                        f"{', '.join(label.root for label in held.root)} are all in the"
                        f" {group.root} group, and an issue carries at most one label of a group."
                    )
                )
        return Ok(spelled)

    def _moved(
        self, held: ProjectName | None, wanted: ProjectName | Cleared | None
    ) -> Result[ProjectName | None, TicketTrackerError]:
        if wanted is None:
            return Ok(held)
        if isinstance(wanted, Cleared):
            return Ok(None)
        match self._project(wanted):
            case Ok(project):
                return Ok(project.name)
            case Err() as failed:
                return failed

    def _pinned(
        self, held: MilestoneName | None, wanted: Milestone | Cleared | None
    ) -> Result[MilestoneName | None, TicketTrackerError]:
        if wanted is None:
            return Ok(held)
        if isinstance(wanted, Cleared):
            return Ok(None)
        project = self._project(wanted.project)
        if isinstance(project, Err):
            return project
        found = project.value.milestones.matching(wanted.name)
        if found is None:
            return Err(
                TicketTrackerError(
                    f"{wanted.project.root} has no milestone named {wanted.name.root}."
                )
            )
        return Ok(found)

    def _status_named(self, name: IssueStatusName) -> Result[IssueStatus, TicketTrackerError]:
        status = self._statuses.matching(name)
        if status is None:
            return Err(TicketTrackerError(f"No status is named {name.root}."))
        return Ok(status)

    def _project(self, name: ProjectName) -> Result[Project, TicketTrackerError]:
        project = self._projects.matching(name)
        if project is None:
            return Err(TicketTrackerError(f"No project is named {name.root}."))
        return Ok(project)

    # Linear counts a blocker as open until it reaches a completed or canceled state.
    def _open_blockers(
        self, tracked: TrackedIssue
    ) -> Result[tuple[IssueIdentifier, ...], TicketTrackerError]:
        finished = StatusNames((*Released.statuses().root, IssueStatusName("Done")))
        still_open: list[IssueIdentifier] = []
        for blocker in tracked.blocked_by:
            found = self._found(blocker)
            if isinstance(found, Err):
                return found
            if finished.matching(found.value.issue.status) is None:
                still_open.append(blocker)
        return Ok(tuple(still_open))

    # A team's group may share its name with a workspace group, yet Linear keeps the two apart.
    def _groups_of(self, team: TeamKey) -> tuple[tuple[LabelGroupName, LabelNames], ...]:
        return (
            *((group, members.label_names()) for group, members in self._groups.items()),
            *(
                (group, members.label_names())
                for (owner, group), members in self._team_groups.items()
                if owner.names(team).root
            ),
        )

    # Groups a test hands in hold labels of no particular color.
    @staticmethod
    def _uncolored(labels: LabelNames) -> ColoredLabels:
        return ColoredLabels(
            tuple(ColoredLabel(name=label, color=LabelColor.fake()) for label in labels.root)
        )

    # Linear reports each label's group on the issue, so the fake reads it from the groups it keeps.
    def _read(self, tracked: TrackedIssue) -> Issue:
        grouped = GroupedLabels(
            tuple(
                GroupedLabel(group=group, label=label)
                for label in tracked.issue.labels.root
                for group, members in self._groups_of(tracked.team)
                if members.matching(label) is not None
            )
        )
        return tracked.issue.model_copy(update={"grouped": grouped})

    def _found(self, issue: IssueIdentifier) -> Result[TrackedIssue, TicketTrackerError]:
        tracked = self._issues.get(issue)
        if tracked is None:
            return Err(TicketTrackerError(f"No issue is identified as {issue.root}."))
        return Ok(tracked)
