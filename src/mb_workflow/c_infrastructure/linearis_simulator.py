import json
from datetime import date
from enum import StrEnum
from subprocess import CalledProcessError
from typing import TYPE_CHECKING

from mb_workflow.b_core.d_domain_model.issue import (
    Assignee,
    CreatedAfter,
    Creator,
    Issue,
    IssueFilter,
    IssueIdentifier,
    Issues,
    LabelName,
    LabelNames,
)
from mb_workflow.c_infrastructure.linear import MorePages, PageCursor
from mb_workflow.c_infrastructure.shell import Command, CommandOutput
from mb_workflow.d_lib.models import Model, Value

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.issue_tracker import TrackedIssue


class PageSize(Value[int]):
    @staticmethod
    def fake() -> PageSize:
        return PageSize(2)


class LabelMode(StrEnum):
    add = "add"
    overwrite = "overwrite"


class ClearLabels(Value[bool]):
    @staticmethod
    def fake() -> ClearLabels:
        return ClearLabels(False)


class Refusal(Value[str]):
    @staticmethod
    def fake() -> Refusal:
        return Refusal("Issue with identifier E-404 not found")


class Node(Value[dict[str, object]]):
    @staticmethod
    def fake() -> Node:
        return Node({"name": LabelName.fake().root})

    @staticmethod
    def of_label(label: LabelName) -> Node:
        return Node({"name": label.root})

    @staticmethod
    def of_issue(issue: Issue) -> Node:
        return Node(
            {
                "identifier": issue.identifier.root,
                "state": {"name": issue.status.root},
                "project": {"name": issue.project.root} if issue.project is not None else None,
                "labels": {"nodes": [Node.of_label(label).root for label in issue.labels.root]},
            }
        )


class Arguments(Model):
    after: PageCursor | None = None
    creator: Creator | None = None
    created_after: CreatedAfter | None = None
    labels: LabelNames | None = None
    label_mode: LabelMode | None = None
    clear_labels: ClearLabels = ClearLabels(False)
    assignee: Assignee | None = None

    @staticmethod
    def fake() -> Arguments:
        return Arguments(after=PageCursor.fake())

    @staticmethod
    def of(flags: Command) -> Arguments:
        found: dict[str, str] = {}
        remaining = list(flags.root)
        while remaining:
            flag = remaining.pop(0).removeprefix("--").replace("-", "_")
            takes_value = len(remaining) > 0 and not remaining[0].startswith("--")
            found[flag] = remaining.pop(0) if takes_value else ""
        labels = found.get("labels")
        created_after = found.get("created_after")
        return Arguments(
            after=PageCursor(found["after"]) if "after" in found else None,
            creator=Creator(found["creator"]) if "creator" in found else None,
            created_after=CreatedAfter(date.fromisoformat(created_after))
            if created_after is not None
            else None,
            labels=LabelNames(tuple(LabelName(name) for name in labels.split(",")))
            if labels is not None
            else None,
            label_mode=LabelMode(found["label_mode"]) if "label_mode" in found else None,
            clear_labels=ClearLabels("clear_labels" in found),
            assignee=Assignee(found["assignee"]) if "assignee" in found else None,
        )

    def wanted(self) -> IssueFilter:
        if self.creator is None or self.created_after is None:
            raise ValueError("linearis issues list is only simulated with a creator and a date")
        return IssueFilter(creator=self.creator, created_after=self.created_after)


class LinearisSimulator:
    """Answers linearis from memory, paging small so every walk crosses a page."""

    def __init__(
        self,
        labels: LabelNames,
        issues: tuple[TrackedIssue, ...],
        page_size: PageSize | None = None,
    ) -> None:
        self._labels = labels
        self._issues = {tracked.issue.identifier: tracked for tracked in issues}
        self._page_size = page_size or PageSize.fake()

    def run(self, command: Command) -> CommandOutput:
        match command.root:
            case ("linearis", "labels", "list", *flags):
                return self._labels_page(Arguments.of(Command(tuple(flags))))
            case ("linearis", "issues", "list", *flags):
                return self._issues_page(Arguments.of(Command(tuple(flags))))
            case ("linearis", "issues", "read", identifier):
                issue = self._tracked(command, IssueIdentifier(identifier)).issue
                return CommandOutput(json.dumps(Node.of_issue(issue).root))
            case ("linearis", "issues", "update", identifier, *flags):
                self._update(
                    command, IssueIdentifier(identifier), Arguments.of(Command(tuple(flags)))
                )
                return CommandOutput("{}")
            case _:
                raise refused(command, Refusal("unknown command"))

    def _labels_page(self, arguments: Arguments) -> CommandOutput:
        nodes = tuple(Node.of_label(label) for label in self._labels.root)
        start = int(arguments.after.root) if arguments.after is not None else 0
        end = start + self._page_size.root
        return page(nodes[start:end], PageCursor(str(end)), MorePages(end < len(nodes)))

    def _issues_page(self, arguments: Arguments) -> CommandOutput:
        wanted = arguments.wanted()
        issues = Issues(
            tuple(
                tracked.issue
                for tracked in self._issues.values()
                if wanted.matches(tracked.creator, tracked.created_on).root
            )
        )
        start = int(arguments.after.root) if arguments.after is not None else 0
        end = start + self._page_size.root
        nodes = tuple(Node.of_issue(issue) for issue in issues.root[start:end])
        return page(nodes, PageCursor(str(end)), MorePages(end < len(issues.root)))

    def _update(self, command: Command, identifier: IssueIdentifier, arguments: Arguments) -> None:
        tracked = self._tracked(command, identifier)
        if arguments.assignee is not None:
            return
        labels = self._labelled(command, tracked.issue.labels, arguments)
        issue = tracked.issue.model_copy(update={"labels": labels})
        self._issues[identifier] = tracked.model_copy(update={"issue": issue})

    def _labelled(self, command: Command, current: LabelNames, arguments: Arguments) -> LabelNames:
        if arguments.clear_labels.root or arguments.labels is None:
            return LabelNames(())
        unknown = [
            label.root for label in arguments.labels.root if not self._labels.has(label).root
        ]
        if unknown:
            raise refused(command, Refusal(f"Label not found: {', '.join(unknown)}"))
        if arguments.label_mode != LabelMode.add:
            return arguments.labels
        labels = current
        for label in arguments.labels.root:
            labels = labels.added(label)
        return labels

    def _tracked(self, command: Command, identifier: IssueIdentifier) -> TrackedIssue:
        tracked = self._issues.get(identifier)
        if tracked is None:
            raise refused(command, Refusal(f"Issue with identifier {identifier.root} not found"))
        return tracked


def page(nodes: tuple[Node, ...], cursor: PageCursor, more: MorePages) -> CommandOutput:
    return CommandOutput(
        json.dumps(
            {
                "nodes": [node.root for node in nodes],
                "pageInfo": {"hasNextPage": more.root, "endCursor": cursor.root},
            }
        )
    )


def refused(command: Command, refusal: Refusal) -> CalledProcessError:
    return CalledProcessError(1, command.root, "", json.dumps({"error": refusal.root}))
