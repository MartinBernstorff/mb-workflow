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

    def added(self, label: LabelName) -> LabelNames:
        if self.has(label).root:
            return self
        return LabelNames((*self.root, label))

    def without(self, label: LabelName) -> LabelNames:
        return LabelNames(tuple(name for name in self.root if name != label))


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


class Issue(Model):
    identifier: IssueIdentifier
    status: StatusName
    project: ProjectName | None
    labels: LabelNames

    @staticmethod
    def fake() -> Issue:
        return Issue(
            identifier=IssueIdentifier.fake(),
            status=StatusName.fake(),
            project=ProjectName.fake(),
            labels=LabelNames.fake(),
        )

    def state(self) -> IssueState | None:
        try:
            return IssueState(self.status.root)
        except ValueError:
            return None


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

    # linearis compares the creation time against midnight of the date, so the day itself is included.
    def matches(self, creator: Creator, created: CreatedOn) -> Matches:
        return Matches(creator == self.creator and created.root >= self.created_after.root)
