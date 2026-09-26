import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from mb_workflow.b_core.d_domain_model.issue import (
    Assignee,
    Clear,
    Issue,
    IssueBody,
    IssueEdit,
    IssueIdentifier,
    IssueReference,
    IssueTitle,
    IssueUrl,
    LabelName,
    LabelNames,
    MilestoneName,
    ProjectName,
)
from mb_workflow.d_lib.models import Model, Value

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.issue_tracker import IssueTracker
    from mb_workflow.c_infrastructure.orca import Orca, Workspace

logger = logging.getLogger(__name__)


class UnlinkedWorktreeError(Exception):
    pass


class InvalidEditError(ValueError):
    pass


class BodyFile(Value[Path]):
    @staticmethod
    def fake() -> BodyFile:
        return BodyFile(Path("body.md"))

    # gh reads the body from stdin when the file is "-".
    def read(self) -> IssueBody:
        if self.root == Path("-"):
            return IssueBody(sys.stdin.read())
        return IssueBody(self.root.read_text())


class RemoveMilestone(Value[bool]):
    @staticmethod
    def fake() -> RemoveMilestone:
        return RemoveMilestone(False)


class EditRequest(Model):
    target: IssueReference | None
    title: IssueTitle | None
    body: IssueBody | None
    body_file: BodyFile | None
    add_labels: LabelNames
    remove_labels: LabelNames
    add_assignee: Assignee | None
    remove_assignee: Assignee | None
    add_project: ProjectName | None
    remove_project: ProjectName | None
    milestone: MilestoneName | None
    remove_milestone: RemoveMilestone

    @staticmethod
    def fake() -> EditRequest:
        return EditRequest.unchanged(None).model_copy(update={"title": IssueTitle.fake()})

    @staticmethod
    def unchanged(target: IssueReference | None) -> EditRequest:
        return EditRequest(
            target=target,
            title=None,
            body=None,
            body_file=None,
            add_labels=LabelNames(()),
            remove_labels=LabelNames(()),
            add_assignee=None,
            remove_assignee=None,
            add_project=None,
            remove_project=None,
            milestone=None,
            remove_milestone=RemoveMilestone(False),
        )

    @staticmethod
    def labelling(label: LabelName) -> EditRequest:
        return EditRequest.unchanged(None).model_copy(update={"add_labels": LabelNames((label,))})

    @staticmethod
    def unlabelling(label: LabelName) -> EditRequest:
        return EditRequest.unchanged(None).model_copy(
            update={"remove_labels": LabelNames((label,))}
        )

    def edit(self, current: Issue, tracker: IssueTracker) -> IssueEdit:
        if self == EditRequest.unchanged(self.target):
            raise InvalidEditError("Specify at least one field to edit.")
        if self.body is not None and self.body_file is not None:
            raise InvalidEditError("Specify only one of --body and --body-file.")
        if self.milestone is not None and self.remove_milestone.root:
            raise InvalidEditError("Specify only one of --milestone and --remove-milestone.")
        return IssueEdit(
            title=self.title,
            body=self.body_file.read() if self.body_file is not None else self.body,
            added_labels=self.add_labels.split(),
            removed_labels=self.remove_labels.split(),
            assignee=self._assignee(current, tracker),
            project=self._project(current),
            milestone=Clear() if self.remove_milestone.root else self.milestone,
        )

    # Linear holds one assignee, so adding one replaces whoever is there.
    def _assignee(self, current: Issue, tracker: IssueTracker) -> Assignee | Clear | None:
        if self.add_assignee is not None:
            return resolved(self.add_assignee, tracker)
        if self.remove_assignee is None or current.assignee is None:
            return None
        removing = resolved(self.remove_assignee, tracker)
        if removing.root.casefold() != current.assignee.root.casefold():
            logger.info("%s is not assigned to %s.", current.identifier.root, removing.root)
            return None
        return Clear()

    # Linear holds one project, so adding one replaces whichever is there.
    def _project(self, current: Issue) -> ProjectName | Clear | None:
        if self.add_project is not None:
            return self.add_project
        if self.remove_project is None or current.project is None:
            return None
        if self.remove_project.root.casefold() != current.project.root.casefold():
            logger.info("%s is not in %s.", current.identifier.root, self.remove_project.root)
            return None
        return Clear()


def resolved(assignee: Assignee, tracker: IssueTracker) -> Assignee:
    return tracker.viewer() if assignee == Assignee.me() else assignee


def issue_from_workspace(workspace: Workspace) -> IssueIdentifier:
    if workspace.linked_linear_issue is None:
        raise UnlinkedWorktreeError(f"{workspace.path.root} has no linked Linear issue")
    return workspace.linked_linear_issue


def edit_issue(orca: Orca, tracker: IssueTracker, request: EditRequest) -> IssueUrl:
    issue = (
        request.target.identifier()
        if request.target is not None
        else issue_from_workspace(orca.current())
    )
    return tracker.edit(issue, request.edit(tracker.read_issue(issue), tracker))
