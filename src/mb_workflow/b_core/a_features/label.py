import logging
from enum import StrEnum
from typing import TYPE_CHECKING

from mb_workflow.c_infrastructure.linear import LabelName, Linear
from mb_workflow.c_infrastructure.orca import Orca
from mb_workflow.d_lib.models import Model

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.workspaces import WorkspaceManager
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
    from mb_workflow.b_core.d_domain_model.workspace import Worktree
    from mb_workflow.c_infrastructure.shell import Shell

logger = logging.getLogger(__name__)


class UnlinkedWorktreeError(Exception):
    pass


class LabelChange(StrEnum):
    add = "add"
    remove = "remove"


class LabelRequest(Model):
    label: LabelName
    change: LabelChange

    @staticmethod
    def fake() -> LabelRequest:
        return LabelRequest(label=LabelName.fake(), change=LabelChange.add)


def labelled_issue(worktree: Worktree) -> IssueIdentifier:
    if worktree.issue is None:
        raise UnlinkedWorktreeError(f"{worktree.path.root} has no linked Linear issue")
    return worktree.issue


def change_label(shell: Shell, request: LabelRequest) -> None:
    changed(Orca(shell), Linear(shell), request)


def changed(workspaces: WorkspaceManager, linear: Linear, request: LabelRequest) -> None:
    issue = labelled_issue(workspaces.current())
    if request.change == LabelChange.remove:
        removed(linear, issue, request.label)
        return
    linear.add_label(issue, request.label)
    logger.info("Added %s to %s.", request.label.root, issue.root)


def removed(linear: Linear, issue: IssueIdentifier, label: LabelName) -> None:
    current = linear.labels(issue)
    remaining = current.without(label)
    if remaining == current:
        logger.info("%s does not carry %s.", issue.root, label.root)
        return
    linear.set_labels(issue, remaining)
    logger.info("Removed %s from %s.", label.root, issue.root)
