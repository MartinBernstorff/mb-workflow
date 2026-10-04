from datetime import date, timedelta
from enum import IntEnum, StrEnum
from typing import TYPE_CHECKING

from mb_workflow.d_lib.models import Model, Value

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.clock import Today


class IssueIdentifier(Value[str]):
    @staticmethod
    def fake() -> IssueIdentifier:
        return IssueIdentifier("E-4289")


class LabelName(Value[str]):
    @staticmethod
    def fake() -> LabelName:
        return LabelName("d-implement")


class LabelKnown(Value[bool]):
    @staticmethod
    def fake() -> LabelKnown:
        return LabelKnown(True)


class LabelNames(Value[tuple[LabelName, ...]]):
    @staticmethod
    def fake() -> LabelNames:
        return LabelNames((LabelName.fake(),))

    def has(self, label: LabelName) -> LabelKnown:
        return LabelKnown(label in self.root)

    def without(self, label: LabelName) -> LabelNames:
        return LabelNames(tuple(name for name in self.root if name != label))

    def replaced(self, label: LabelName, replacement: LabelName) -> LabelNames:
        return LabelNames(tuple(replacement if name == label else name for name in self.root))

    # Linear resolves a label name ignoring case, so these three take a workspace's labels as self.
    def matching(self, label: LabelName) -> LabelName | None:
        wanted = label.root.casefold()
        return next((known for known in self.root if known.root.casefold() == wanted), None)

    def unmatched(self, requested: LabelNames) -> LabelNames:
        return LabelNames(tuple(label for label in requested.root if self.matching(label) is None))

    def spelled(self, requested: LabelNames) -> LabelNames:
        matched = (self.matching(label) for label in requested.root)
        return LabelNames(tuple(dict.fromkeys(known for known in matched if known is not None)))

    def split(self) -> LabelNames:
        return LabelNames(
            tuple(
                LabelName(part.strip())
                for label in self.root
                for part in label.root.split(",")
                if part.strip()
            )
        )


# Linear writes a label's color as a hex code, in whichever case it was given.
class LabelColor(Value[str]):
    @staticmethod
    def fake() -> LabelColor:
        return LabelColor.grey()

    @staticmethod
    def yellow() -> LabelColor:
        return LabelColor("#f2c94c")

    @staticmethod
    def grey() -> LabelColor:
        return LabelColor("#bec2c8")

    def matches(self, other: LabelColor) -> Matches:
        return Matches(self.root.casefold() == other.root.casefold())


class ColoredLabel(Model):
    name: LabelName
    color: LabelColor

    @staticmethod
    def fake() -> ColoredLabel:
        return ColoredLabel(name=LabelName.fake(), color=LabelColor.fake())


class ColoredLabels(Value[tuple[ColoredLabel, ...]]):
    @staticmethod
    def fake() -> ColoredLabels:
        return ColoredLabels((ColoredLabel.fake(),))

    def label_names(self) -> LabelNames:
        return LabelNames(tuple(label.name for label in self.root))


class TicketCount(Value[int]):
    @staticmethod
    def fake() -> TicketCount:
        return TicketCount(1)


class LabelGroupName(Value[str]):
    @staticmethod
    def fake() -> LabelGroupName:
        return LabelGroupName("flow")


class GroupedLabel(Model):
    group: LabelGroupName
    label: LabelName

    @staticmethod
    def fake() -> GroupedLabel:
        return GroupedLabel(group=LabelGroupName.fake(), label=LabelName("todo"))


class GroupedLabels(Value[tuple[GroupedLabel, ...]]):
    @staticmethod
    def fake() -> GroupedLabels:
        return GroupedLabels((GroupedLabel.fake(),))

    # Linear resolves a group name ignoring case, as it does a label name.
    def in_group(self, group: LabelGroupName) -> LabelNames:
        wanted = group.root.casefold()
        return LabelNames(
            tuple(held.label for held in self.root if held.group.root.casefold() == wanted)
        )


# ProjectName and StatusName share a base so one exclusion pattern can match either.
class IssueText(Value[str]):
    def names(self, other: IssueText) -> Matches:
        return Matches(self.root.casefold() == other.root.casefold())


class ProjectName(IssueText):
    @staticmethod
    def fake() -> ProjectName:
        return ProjectName("BE: Campaigns MVP")


class IssueStatusName(IssueText):
    @staticmethod
    def fake() -> IssueStatusName:
        return IssueStatusName("Todo")


class StatusNames(Value[tuple[IssueStatusName, ...]]):
    @staticmethod
    def fake() -> StatusNames:
        return StatusNames(
            (IssueStatusName.fake(), IssueStatusName("In Progress"), IssueStatusName("Done"))
        )

    @staticmethod
    def closed() -> StatusNames:
        return StatusNames((IssueStatusName("Canceled"), IssueStatusName("Duplicate")))

    def matching(self, status: IssueStatusName) -> IssueStatusName | None:
        return next((known for known in self.root if known.names(status).root), None)


class StatusType(StrEnum):
    triage = "triage"
    backlog = "backlog"
    unstarted = "unstarted"
    started = "started"
    completed = "completed"
    canceled = "canceled"


class StatusTypes(Value[tuple[StatusType, ...]]):
    @staticmethod
    def fake() -> StatusTypes:
        return StatusTypes((StatusType.completed,))

    def has(self, status_type: StatusType) -> Matches:
        return Matches(status_type in self.root)


class IssueStatus(Model):
    name: IssueStatusName
    type: StatusType

    @staticmethod
    def fake() -> IssueStatus:
        return IssueStatus(name=IssueStatusName.fake(), type=StatusType.unstarted)


class IssueStatuses(Value[tuple[IssueStatus, ...]]):
    @staticmethod
    def fake() -> IssueStatuses:
        return IssueStatuses(
            (
                IssueStatus.fake(),
                IssueStatus(name=IssueStatusName("In Progress"), type=StatusType.started),
                IssueStatus(name=IssueStatusName("Done"), type=StatusType.completed),
            )
        )

    def matching(self, name: IssueStatusName) -> IssueStatus | None:
        return next((known for known in self.root if known.name.names(name).root), None)


class Assigned(Value[bool]):
    @staticmethod
    def fake() -> Assigned:
        return Assigned(False)


class Issue(Model):
    identifier: IssueIdentifier
    status: IssueStatusName
    project: ProjectName | None
    labels: LabelNames
    grouped: GroupedLabels
    assigned: Assigned

    @staticmethod
    def fake() -> Issue:
        return Issue(
            identifier=IssueIdentifier.fake(),
            status=IssueStatusName.fake(),
            project=ProjectName.fake(),
            labels=LabelNames.fake(),
            grouped=GroupedLabels(()),
            assigned=Assigned.fake(),
        )


class IssueTitle(Value[str]):
    @staticmethod
    def fake() -> IssueTitle:
        return IssueTitle("Add widget")


class IssueDescription(Value[str]):
    @staticmethod
    def fake() -> IssueDescription:
        return IssueDescription("The dashboard needs a widget.")


class MilestoneName(IssueText):
    @staticmethod
    def fake() -> MilestoneName:
        return MilestoneName("Beta")


class MilestoneNames(Value[tuple[MilestoneName, ...]]):
    @staticmethod
    def fake() -> MilestoneNames:
        return MilestoneNames((MilestoneName.fake(),))

    def matching(self, milestone: MilestoneName) -> MilestoneName | None:
        return next((known for known in self.root if known.names(milestone).root), None)


class Project(Model):
    name: ProjectName
    milestones: MilestoneNames

    @staticmethod
    def fake() -> Project:
        return Project(name=ProjectName.fake(), milestones=MilestoneNames.fake())


class Projects(Value[tuple[Project, ...]]):
    @staticmethod
    def fake() -> Projects:
        return Projects((Project.fake(),))

    def matching(self, project: ProjectName) -> Project | None:
        return next((known for known in self.root if known.name.names(project).root), None)


# Numbered as Linear numbers them, so tickets read their priority without translation.
class Priority(IntEnum):
    no_priority = 0
    urgent = 1
    high = 2
    medium = 3
    low = 4


class IssueDetail(Model):
    issue: Issue
    title: IssueTitle
    description: IssueDescription | None
    assignee: Assignee | None
    milestone: MilestoneName | None
    priority: Priority
    blocks: frozenset[IssueIdentifier]
    blocked_by: frozenset[IssueIdentifier]

    @staticmethod
    def fake() -> IssueDetail:
        return IssueDetail(
            issue=Issue.fake(),
            title=IssueTitle.fake(),
            description=IssueDescription.fake(),
            assignee=None,
            milestone=MilestoneName.fake(),
            priority=Priority.medium,
            blocks=frozenset(),
            blocked_by=frozenset(),
        )


class Issues(Value[tuple[Issue, ...]]):
    @staticmethod
    def fake() -> Issues:
        return Issues((Issue.fake(),))

    def identifiers(self) -> tuple[IssueIdentifier, ...]:
        return tuple(issue.identifier for issue in self.root)


class Assignee(Value[str]):
    @staticmethod
    def fake() -> Assignee:
        return Assignee("mab@flowbase.io")

    @staticmethod
    def me() -> Assignee:
        return Assignee("@me")

    def resolved(self, viewer: Assignee) -> Assignee:
        return viewer if self == Assignee.me() else self


# Stands for a field the update empties, where None means the update leaves it alone.
class Cleared(Model):
    @staticmethod
    def fake() -> Cleared:
        return Cleared()


class Milestone(Model):
    project: ProjectName
    name: MilestoneName

    @staticmethod
    def fake() -> Milestone:
        return Milestone(project=ProjectName.fake(), name=MilestoneName.fake())


class IssueUpdate(Model):
    title: IssueTitle | None
    description: IssueDescription | None
    labels: LabelNames | None
    assignee: Assignee | Cleared | None
    project: ProjectName | Cleared | None
    status: IssueStatusName | None
    milestone: Milestone | Cleared | None
    priority: Priority | None
    blocks: tuple[IssueIdentifier, ...]
    blocked_by: tuple[IssueIdentifier, ...]

    @staticmethod
    def fake() -> IssueUpdate:
        return IssueUpdate(
            title=IssueTitle.fake(),
            description=IssueDescription.fake(),
            labels=LabelNames.fake(),
            assignee=Assignee.fake(),
            project=ProjectName.fake(),
            status=IssueStatusName.fake(),
            milestone=Milestone.fake(),
            priority=Priority.medium,
            blocks=(),
            blocked_by=(),
        )

    @staticmethod
    def nothing() -> IssueUpdate:
        return IssueUpdate(
            title=None,
            description=None,
            labels=None,
            assignee=None,
            project=None,
            status=None,
            milestone=None,
            priority=None,
            blocks=(),
            blocked_by=(),
        )


class TeamKey(IssueText):
    @staticmethod
    def fake() -> TeamKey:
        return TeamKey("E")


class TeamName(IssueText):
    @staticmethod
    def fake() -> TeamName:
        return TeamName("Engineering")


class Team(Model):
    key: TeamKey
    name: TeamName
    projects: tuple[ProjectName, ...]

    @staticmethod
    def fake() -> Team:
        return Team(key=TeamKey.fake(), name=TeamName.fake(), projects=(ProjectName.fake(),))


class NewIssue(Model):
    team: TeamKey | None
    title: IssueTitle
    description: IssueDescription | None
    labels: LabelNames
    assignee: Assignee | None
    project: ProjectName | None
    status: IssueStatusName
    milestone: Milestone | None
    priority: Priority | None
    blocks: tuple[IssueIdentifier, ...]
    blocked_by: tuple[IssueIdentifier, ...]

    @staticmethod
    def fake() -> NewIssue:
        return NewIssue(
            team=None,
            title=IssueTitle.fake(),
            description=IssueDescription.fake(),
            labels=LabelNames.fake(),
            assignee=Assignee.fake(),
            project=ProjectName.fake(),
            status=IssueStatusName.fake(),
            milestone=Milestone.fake(),
            priority=Priority.medium,
            blocks=(),
            blocked_by=(),
        )


class IssueUrl(Value[str]):
    @staticmethod
    def fake() -> IssueUrl:
        return IssueUrl("https://linear.app/flowbase/issue/E-4289/add-widget")


class CreatedIssue(Model):
    identifier: IssueIdentifier
    url: IssueUrl

    @staticmethod
    def fake() -> CreatedIssue:
        return CreatedIssue(identifier=IssueIdentifier.fake(), url=IssueUrl.fake())


class Creator(Value[str]):
    @staticmethod
    def fake() -> Creator:
        return Creator("mab@flowbase.io")


class CreatedWithin(Value[int]):
    @staticmethod
    def fake() -> CreatedWithin:
        return CreatedWithin(30)


class CreatedOn(Value[date]):
    @staticmethod
    def fake() -> CreatedOn:
        return CreatedOn(date(2026, 9, 1))


class CreatedAfter(Value[date]):
    @staticmethod
    def fake() -> CreatedAfter:
        return CreatedAfter(date(2026, 8, 9))

    @staticmethod
    def of(window: CreatedWithin, today: Today) -> CreatedAfter:
        return CreatedAfter(today.root - timedelta(days=window.root))


class Matches(Value[bool]):
    @staticmethod
    def fake() -> Matches:
        return Matches(True)


class IssueFilter(Model):
    creator: Creator
    created_after: CreatedAfter

    @staticmethod
    def fake() -> IssueFilter:
        return IssueFilter(creator=Creator.fake(), created_after=CreatedAfter.fake())

    # Linear compares the creation time against midnight of the date, so the day itself is included.
    def matches(self, creator: Creator, created: CreatedOn) -> Matches:
        return Matches(creator == self.creator and created.root >= self.created_after.root)
