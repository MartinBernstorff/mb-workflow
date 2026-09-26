import logging
from enum import StrEnum
from typing import TYPE_CHECKING

from mb_workflow.b_core.d_domain_model.issue import LabelName
from mb_workflow.c_infrastructure.linear import Linear
from mb_workflow.c_infrastructure.orca import Orca, Worktree
from mb_workflow.d_lib.models import Model

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.issue_tracker import IssueTracker
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
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
    if worktree.linked_linear_issue is None:
        raise UnlinkedWorktreeError(f"{worktree.path.root} has no linked Linear issue")
    return worktree.linked_linear_issue


def change_label(shell: Shell, request: LabelRequest) -> None:
    changed(Orca(shell), Linear(shell), request)


def changed(orca: Orca, tracker: IssueTracker, request: LabelRequest) -> None:
    issue = labelled_issue(orca.current())
    if request.change == LabelChange.remove:
        removed(tracker, issue, request.label)
        return
    tracker.add_label(issue, request.label)
    logger.info("Added %s to %s.", request.label.root, issue.root)


def removed(tracker: IssueTracker, issue: IssueIdentifier, label: LabelName) -> None:
    current = tracker.read(issue).labels
    remaining = current.without(label)
    if remaining == current:
        logger.info("%s does not carry %s.", issue.root, label.root)
        return
    tracker.set_labels(issue, remaining)
    logger.info("Removed %s from %s.", label.root, issue.root)
