import logging
import sys

from mb_workflow.config import (
    ConfigFileName,
    Configuration,
    InvalidConfigError,
    LinearTracker,
    MissingConfigError,
    TodoistTracker,
    WorkingDirectory,
)
from mb_workflow.issue import IssueIdentifier
from mb_workflow.models import Value
from mb_workflow.shell import ExitCode
from mb_workflow.workspace.link import (
    InvalidLinkError,
    LinearTicketLinkStore,
    MissingLinkError,
    SuppliedTicket,
    TicketLinkStore,
    TodoistTaskId,
    TodoistTicketLinkStore,
    WorkspaceRoot,
)

logger = logging.getLogger(__name__)

type LinkedTicket = TodoistTaskId | IssueIdentifier


class FlowReport(Value[str]):
    @staticmethod
    def fake() -> FlowReport:
        return FlowReport.of(Configuration.fake(), TodoistTaskId.fake())

    @staticmethod
    def of(config: Configuration, linked: LinkedTicket | None) -> FlowReport:
        settings = config.settings
        recorded = linked.root if linked is not None else "none"
        match settings.issues:
            case TodoistTracker() as todoist:
                issues = (
                    f"tracker: {todoist.tracker}",
                    f"project tag: {todoist.project_tag.root}",
                    f"task: {recorded}",
                )
            case LinearTracker() as linear:
                issues = (f"tracker: {linear.tracker}", f"issue: {recorded}")
        return FlowReport(
            "\n".join(
                (
                    *issues,
                    f"status store: {settings.status.store}",
                    f"origin: {config.origin.root}",
                )
            )
        )


def shown[T: (TodoistTaskId, IssueIdentifier)](
    config: Configuration, store: TicketLinkStore[T]
) -> FlowReport:
    return FlowReport.of(config, store.read())


# The tracker decides which identifier the workspace links, so each arm binds its own store.
def reported(config: Configuration) -> FlowReport:
    workspace = WorkspaceRoot.of(config.origin)
    match config.settings.issues:
        case TodoistTracker():
            return shown(config, TodoistTicketLinkStore.at(workspace))
        case LinearTracker():
            return shown(config, LinearTicketLinkStore.at(workspace))


def show(directory: WorkingDirectory, name: ConfigFileName) -> ExitCode:
    try:
        config = Configuration.resolved(directory, name)
        report = reported(config)
    except (InvalidConfigError, InvalidLinkError, MissingConfigError, OSError) as error:
        logger.error("%s", error)
        return ExitCode(1)
    _ = sys.stdout.write(f"{report.root}\n")
    return ExitCode(0)


def linked[T: (TodoistTaskId, IssueIdentifier)](
    store: TicketLinkStore[T], supplied: SuppliedTicket | None
) -> T:
    return store.resolve(supplied)


def resolved(config: Configuration, supplied: SuppliedTicket | None) -> LinkedTicket:
    workspace = WorkspaceRoot.of(config.origin)
    match config.settings.issues:
        case TodoistTracker():
            return linked(TodoistTicketLinkStore.at(workspace), supplied)
        case LinearTracker():
            return linked(LinearTicketLinkStore.at(workspace), supplied)


def link(
    directory: WorkingDirectory, name: ConfigFileName, supplied: SuppliedTicket | None
) -> ExitCode:
    try:
        config = Configuration.resolved(directory, name)
        recorded = resolved(config, supplied)
    except (
        InvalidConfigError,
        InvalidLinkError,
        MissingConfigError,
        MissingLinkError,
        OSError,
        ValueError,
    ) as error:
        logger.error("%s", error)
        return ExitCode(1)
    _ = sys.stdout.write(f"{recorded.root}\n")
    return ExitCode(0)
