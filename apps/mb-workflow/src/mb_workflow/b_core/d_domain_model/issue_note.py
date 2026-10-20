import re
from enum import StrEnum

import yaml
from pydantic import ConfigDict, JsonValue, ValidationError, field_validator
from safe_result import Err, Ok, Result, safe_with

from mb_workflow.b_core.d_domain_model.issue import (
    Assignee,
    Cleared,
    IssueDescription,
    IssueDetail,
    IssueSnapshot,
    IssueStatusName,
    IssueTitle,
    IssueUpdate,
    LabelNames,
    Priority,
)
from mb_workflow.b_core.d_domain_model.list_indent import ListIndent
from mb_workflow.d_lib.models import Model, Value


class InvalidNoteError(Exception):
    pass


class NoteText(Value[str]):
    @staticmethod
    def fake() -> NoteText:
        return IssueNote.rendered(IssueSnapshot.fake())


# An issue's title as it can stand in a file name. Characters that file systems or Obsidian links
# reserve become "-", and a long title is cut short.
class NoteTitle(Value[str]):
    @staticmethod
    def fake() -> NoteTitle:
        return NoteTitle.of(IssueTitle.fake())

    @staticmethod
    def of(title: IssueTitle) -> NoteTitle:
        replaced = re.sub(r"[/:\[\]#^|]", "-", title.root)
        cut = replaced.encode()[:200].decode(errors="ignore")
        return NoteTitle(cut.strip().lstrip("."))

    # A title that only differs from the issue's by what a file name cannot hold is unchanged.
    def renames(self, title: IssueTitle) -> IssueTitle | None:
        return None if self == NoteTitle.of(title) else IssueTitle(self.root)


class NotePriority(StrEnum):
    no_priority = "none"
    urgent = "urgent"
    high = "high"
    medium = "medium"
    low = "low"

    @staticmethod
    def of(priority: Priority) -> NotePriority:
        return NotePriority[priority.name]

    def to_priority(self) -> Priority:
        return Priority[self.name]


# The fields a note may change. The rest of its frontmatter mirrors Linear, and edits to it are ignored.
class NoteFrontmatter(Model):
    model_config = ConfigDict(extra="ignore", frozen=True)

    status: IssueStatusName
    labels: LabelNames = LabelNames(())
    assignee: Assignee | None = None
    priority: NotePriority = NotePriority.no_priority

    @staticmethod
    def fake() -> NoteFrontmatter:
        return NoteFrontmatter(
            status=IssueStatusName.fake(),
            labels=LabelNames.fake(),
            assignee=None,
            priority=NotePriority.medium,
        )

    # Obsidian writes an emptied list or text property as a bare key, which YAML reads as null.
    @field_validator("labels", mode="before")
    @classmethod
    def _no_labels_when_empty(cls, value: JsonValue) -> JsonValue:
        return [] if value is None else value

    @field_validator("assignee", mode="before")
    @classmethod
    def _no_assignee_when_empty(cls, value: JsonValue) -> JsonValue:
        return None if value == "" else value


class IssueNote(Model):
    frontmatter: NoteFrontmatter
    description: IssueDescription

    @staticmethod
    def fake() -> IssueNote:
        return IssueNote(frontmatter=NoteFrontmatter.fake(), description=IssueDescription.fake())

    @staticmethod
    def rendered(snapshot: IssueSnapshot) -> NoteText:
        detail = snapshot.detail
        frontmatter = {
            "status": detail.issue.status.root,
            "labels": [label.root for label in detail.issue.labels.root],
            "assignee": detail.assignee.root if detail.assignee is not None else None,
            "priority": NotePriority.of(detail.priority).value,
            "project": detail.issue.project.root if detail.issue.project is not None else None,
            "milestone": detail.milestone.root if detail.milestone is not None else None,
            "estimate": detail.estimate.root if detail.estimate is not None else None,
            "url": snapshot.url.root,
        }
        dumped = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
        return NoteText(f"---\n{dumped}---\n\n{IssueNote.body_of(detail).root}\n")

    # Linear escapes the brackets of a [[wiki-link]] in markdown, which would break the link in
    # Obsidian, and indents nested list items with spaces where Obsidian uses tabs.
    @staticmethod
    def body_of(detail: IssueDetail) -> IssueDescription:
        held = detail.description.root.strip() if detail.description is not None else ""
        linked = IssueDescription(re.sub(r"\\\[\\\[(.+?)\\\]\\\]", r"[[\1]]", held))
        return ListIndent.obsidian.indented(linked)

    @staticmethod
    def parsed(text: NoteText) -> Result[IssueNote, InvalidNoteError]:
        found = re.fullmatch(r"---\n(.*?)\n---[ \t]*(?:\n(.*))?", text.root, re.DOTALL)
        if found is None:
            return Err(InvalidNoteError("The note does not start with a --- frontmatter block."))
        match safe_with(yaml.YAMLError)(yaml.safe_load)(found.group(1)):
            case Ok(loaded):
                pass
            case Err(error):
                return Err(InvalidNoteError(f"The frontmatter is not valid YAML. {error}"))
        match safe_with(ValidationError)(NoteFrontmatter.model_validate)(loaded):
            case Ok(frontmatter):
                pass
            case Err(error):
                return Err(InvalidNoteError(f"The frontmatter is not valid. {error}"))
        body = found.group(2) or ""
        return Ok(IssueNote(frontmatter=frontmatter, description=IssueDescription(body.strip())))

    # Sets only the fields the note changes, so a note that matches the issue updates nothing. The
    # title lives in the note's file name; a note named without one leaves the title alone.
    def update_of(self, detail: IssueDetail, title: NoteTitle | None) -> IssueUpdate:
        wanted = self.frontmatter
        held_description = IssueNote.body_of(detail)
        held_labels = {label.root.casefold() for label in detail.issue.labels.root}
        wanted_labels = {label.root.casefold() for label in wanted.labels.root}
        held_assignee = detail.assignee.root.casefold() if detail.assignee is not None else None
        wanted_assignee = wanted.assignee.root.casefold() if wanted.assignee is not None else None
        return IssueUpdate(
            title=title.renames(detail.title) if title is not None else None,
            description=(
                ListIndent.linear.indented(self.description)
                if ListIndent.obsidian.indented(self.description) != held_description
                else None
            ),
            labels=wanted.labels if wanted_labels != held_labels else None,
            assignee=((wanted.assignee or Cleared()) if wanted_assignee != held_assignee else None),
            project=None,
            status=None if detail.issue.status.names(wanted.status).root else wanted.status,
            milestone=None,
            priority=(
                wanted.priority.to_priority()
                if wanted.priority.to_priority() != detail.priority
                else None
            ),
            estimate=None,
            blocks=(),
            blocked_by=(),
        )
