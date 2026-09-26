from datetime import date, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

from mb_workflow.d_lib.models import Model, Value

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.clock import Today


class IssueIdentifier(Value[str]):
    @staticmethod
    def fake() -> IssueIdentifier:
        return IssueIdentifier("E-4289")


class BranchSlug(Value[str]):
    @staticmethod
    def fake() -> BranchSlug:
        return BranchSlug(f"mab/{IssueIdentifier.fake().root.lower()}-feat-add-widget")


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

    # Linear resolves a label name ignoring case, so these three take a workspace's labels as self.
    def matching(self, label: LabelName) -> LabelName | None:
        wanted = label.root.casefold()
        return next((known for known in self.root if known.root.casefold() == wanted), None)

    def unmatched(self, requested: LabelNames) -> LabelNames:
        return LabelNames(tuple(label for label in requested.root if self.matching(label) is None))

    def spelled(self, requested: LabelNames) -> LabelNames:
        matched = (self.matching(label) for label in requested.root)
        return LabelNames(tuple(dict.fromkeys(known for known in matched if known is not None)))


# ProjectName and StatusName share a base so one exclusion pattern can match either.
class IssueText(Value[str]): ...


class ProjectName(IssueText):
    @staticmethod
    def fake() -> ProjectName:
        return ProjectName("BE: Campaigns MVP")


class StatusName(IssueText):
    @staticmethod
    def fake() -> StatusName:
        return StatusName("Todo")


class IssueState(StrEnum):
    backlog = "Backlog"
    maturing = "Maturing"
    todo = "Todo"
    in_progress = "In Progress"
    in_review = "In Review"
    ready_for_release = "Ready For Release"
    done = "Done"
    canceled = "Canceled"
    duplicate = "Duplicate"
    triage = "Triage"


class Assigned(Value[bool]):
    @staticmethod
    def fake() -> Assigned:
        return Assigned(False)


class Issue(Model):
    identifier: IssueIdentifier
    status: StatusName
    project: ProjectName | None
    labels: LabelNames
    assigned: Assigned

    @staticmethod
    def fake() -> Issue:
        return Issue(
            identifier=IssueIdentifier.fake(),
            status=StatusName.fake(),
            project=ProjectName.fake(),
            labels=LabelNames.fake(),
            assigned=Assigned.fake(),
        )

    def state(self) -> IssueState | None:
        try:
            return IssueState(self.status.root)
        except ValueError:
            return None


class IssueTitle(Value[str]):
    @staticmethod
    def fake() -> IssueTitle:
        return IssueTitle("Add widget")


class IssueDescription(Value[str]):
    @staticmethod
    def fake() -> IssueDescription:
        return IssueDescription("The dashboard needs a widget.")


class IssueDetail(Model):
    issue: Issue
    title: IssueTitle
    description: IssueDescription | None

    @staticmethod
    def fake() -> IssueDetail:
        return IssueDetail(
            issue=Issue.fake(), title=IssueTitle.fake(), description=IssueDescription.fake()
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
