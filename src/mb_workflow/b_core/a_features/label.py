import logging
from enum import StrEnum
from typing import TYPE_CHECKING

from mb_workflow.b_core.d_domain_model.issue import LabelName
from mb_workflow.d_lib.models import Model

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManager
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
    from mb_workflow.b_core.d_domain_model.workspace import Worktree

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


def issue_from_workspace(worktree: Worktree) -> IssueIdentifier:
    if worktree.issue is None:
        raise UnlinkedWorktreeError(
            f"{worktree.path.root} has no linked Linear issue. Link one with `mw link <ticket>`."
        )
    return worktree.issue


def change_label(manager: WorkspaceManager, tracker: TicketTracker, request: LabelRequest) -> None:
    issue = issue_from_workspace(manager.current())
    if request.change == LabelChange.remove:
        remove_label(tracker, issue, request.label)
        return
    tracker.add_label(issue, request.label)
    logger.info("Added %s to %s.", request.label.root, issue.root)


def remove_label(tracker: TicketTracker, issue: IssueIdentifier, label: LabelName) -> None:
    current = tracker.read_issue(issue).labels
    remaining = current.without(label)
    if remaining == current:
        logger.info("%s does not carry %s.", issue.root, label.root)
        return
    tracker.set_labels(issue, remaining)
    logger.info("Removed %s from %s.", label.root, issue.root)
