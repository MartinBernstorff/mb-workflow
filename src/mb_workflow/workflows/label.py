import logging
from enum import StrEnum
from subprocess import CalledProcessError
from typing import TYPE_CHECKING

from mb_workflow.config import (
    ConfigFileName,
    Configuration,
    InvalidConfigError,
    LinearTracker,
    MissingConfigError,
    TodoistTracker,
    WorkingDirectory,
)
from mb_workflow.models import Model
from mb_workflow.shell import ExitCode, Shell
from mb_workflow.trackers.linear import LabelName, Linear
from mb_workflow.workspace.link import (
    InvalidLinkError,
    LinearTicketLinkStore,
    TicketLinkStore,
    WorkspaceRoot,
)

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


def labelled_issue(store: TicketLinkStore[IssueIdentifier]) -> IssueIdentifier:
    recorded = store.read()
    if recorded is None:
        raise UnlinkedWorktreeError(
            f"No Linear issue is linked to this workspace. Record one with `mw flow link` "
            f"to write it to {store.location().root}."
        )
    return recorded


def linear_link(config: Configuration) -> TicketLinkStore[IssueIdentifier]:
    match config.settings.issues:
        case LinearTracker():
            return LinearTicketLinkStore.at(WorkspaceRoot.of(config.origin))
        case TodoistTracker():
            raise UnlinkedWorktreeError(
                f"{config.origin.root} tracks issues on Todoist, so there is no Linear issue to label."
            )


def change_label(
    shell: Shell, directory: WorkingDirectory, name: ConfigFileName, request: LabelRequest
) -> ExitCode:
    try:
        config = Configuration.resolved(directory, name)
        return changed(Linear(shell), linear_link(config), request)
    except FileNotFoundError as error:
        logger.error("%s is not installed or not on PATH.", error.filename)
        return ExitCode(1)
    except (
        CalledProcessError,
        InvalidConfigError,
        InvalidLinkError,
        MissingConfigError,
        OSError,
        UnlinkedWorktreeError,
        ValueError,
    ) as error:
        logger.error("%s", error)
        return ExitCode(1)


def changed(
    linear: Linear, store: TicketLinkStore[IssueIdentifier], request: LabelRequest
) -> ExitCode:
    issue = labelled_issue(store)
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
