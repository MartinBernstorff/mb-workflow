import re
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


class UnreadableReferenceError(ValueError):
    pass


# An identifier or the issue's URL, as `gh pr edit` takes a number or a URL.
class IssueReference(Value[str]):
    @staticmethod
    def fake() -> IssueReference:
        return IssueReference(
            f"https://linear.app/flowbase/issue/{IssueIdentifier.fake().root}/add-widget"
        )

    def identifier(self) -> IssueIdentifier:
        found = re.fullmatch(r"(?:.*/issue/)?([A-Za-z][A-Za-z0-9]*-\d+)(?:/.*)?", self.root.strip())
        if found is None:
            raise UnreadableReferenceError(
                f"{self.root} is neither an issue identifier nor its URL."
            )
        return IssueIdentifier(found.group(1).upper())


class IssueUrl(Value[str]):
    @staticmethod
    def fake() -> IssueUrl:
        return IssueUrl(IssueReference.fake().root)


class IssueTitle(Value[str]):
    @staticmethod
    def fake() -> IssueTitle:
        return IssueTitle("Add a widget")


class IssueBody(Value[str]):
    @staticmethod
    def fake() -> IssueBody:
        return IssueBody("The widget goes on the dashboard.")


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

    # gh takes a label flag as one name or several separated by commas.
    def split(self) -> LabelNames:
        return LabelNames(
            tuple(
                LabelName(part.strip())
                for label in self.root
                for part in label.root.split(",")
                if part.strip()
            )
        )

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


class MilestoneName(Value[str]):
    @staticmethod
    def fake() -> MilestoneName:
        return MilestoneName("Beta")


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


class Assignee(Value[str]):
    @staticmethod
    def fake() -> Assignee:
        return Assignee("mab@flowbase.io")

    # gh's shorthand for whoever is signed in.
    @staticmethod
    def me() -> Assignee:
        return Assignee("@me")


class Issue(Model):
    identifier: IssueIdentifier
    title: IssueTitle
    body: IssueBody
    status: StatusName
    project: ProjectName | None
    milestone: MilestoneName | None
    labels: LabelNames
    assignee: Assignee | None

    @staticmethod
    def fake() -> Issue:
        return Issue(
            identifier=IssueIdentifier.fake(),
            title=IssueTitle.fake(),
            body=IssueBody.fake(),
            status=StatusName.fake(),
            project=ProjectName.fake(),
            milestone=None,
            labels=LabelNames.fake(),
            assignee=None,
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


class Clear(Model):
    @staticmethod
    def fake() -> Clear:
        return Clear()


# A None field is left as it is; Clear empties it.
class IssueEdit(Model):
    title: IssueTitle | None
    body: IssueBody | None
    added_labels: LabelNames
    removed_labels: LabelNames
    assignee: Assignee | Clear | None
    project: ProjectName | Clear | None
    milestone: MilestoneName | Clear | None

    @staticmethod
    def fake() -> IssueEdit:
        return IssueEdit.unchanged().model_copy(update={"title": IssueTitle.fake()})

    @staticmethod
    def unchanged() -> IssueEdit:
        return IssueEdit(
            title=None,
            body=None,
            added_labels=LabelNames(()),
            removed_labels=LabelNames(()),
            assignee=None,
            project=None,
            milestone=None,
        )
