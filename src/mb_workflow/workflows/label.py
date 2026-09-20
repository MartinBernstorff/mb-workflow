import logging
from enum import StrEnum
from subprocess import CalledProcessError
from typing import TYPE_CHECKING

from mb_workflow.models import Model
from mb_workflow.shell import ExitCode, Shell
from mb_workflow.trackers.linear import LabelName, Linear
from mb_workflow.workspace.orca import Orca, OrcaError, Worktree

if TYPE_CHECKING:
    from mb_workflow.issue import IssueIdentifier

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


def change_label(shell: Shell, request: LabelRequest) -> ExitCode:
    try:
        return changed(Orca(shell), Linear(shell), request)
    except FileNotFoundError as error:
        logger.error("%s is not installed or not on PATH.", error.filename)
        return ExitCode(1)
    except (CalledProcessError, OrcaError, UnlinkedWorktreeError, ValueError) as error:
        logger.error("%s", error)
        return ExitCode(1)


def changed(orca: Orca, linear: Linear, request: LabelRequest) -> ExitCode:
    issue = labelled_issue(orca.current())
    if request.change == LabelChange.remove:
        return removed(linear, issue, request.label)
    linear.add_label(issue, request.label)
    logger.info("Added %s to %s.", request.label.root, issue.root)
    return ExitCode(0)


def removed(linear: Linear, issue: IssueIdentifier, label: LabelName) -> ExitCode:
    current = linear.labels(issue)
    remaining = current.without(label)
    if remaining == current:
        logger.info("%s does not carry %s.", issue.root, label.root)
        return ExitCode(0)
    linear.set_labels(issue, remaining)
    logger.info("Removed %s from %s.", label.root, issue.root)
    return ExitCode(0)
