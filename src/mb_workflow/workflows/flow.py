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
from mb_workflow.link import (
    InvalidLinkError,
    MissingLinkError,
    TaskId,
    WorkspaceLink,
    WorkspaceRoot,
)
from mb_workflow.models import Value
from mb_workflow.shell import ExitCode

logger = logging.getLogger(__name__)


class FlowReport(Value[str]):
    @staticmethod
    def fake() -> FlowReport:
        return FlowReport.of(Configuration.fake(), TaskId.fake())

    @staticmethod
    def of(config: Configuration, task: TaskId | None) -> FlowReport:
        settings = config.settings
        match settings.issues:
            case TodoistTracker() as todoist:
                linked = task.root if task is not None else "none"
                issues = (
                    f"tracker: {todoist.tracker}",
                    f"project tag: {todoist.project_tag.root}",
                    f"task: {linked}",
                )
            case LinearTracker() as linear:
                issues = (f"tracker: {linear.tracker}",)
        return FlowReport(
            "\n".join(
                (
                    *issues,
                    f"status store: {settings.status.store}",
                    f"origin: {config.origin.root}",
                )
            )
        )


def workspace_link(config: Configuration) -> WorkspaceLink:
    return WorkspaceLink(workspace=WorkspaceRoot(config.origin.root.parent))


def linked_task(config: Configuration) -> TaskId | None:
    match config.settings.issues:
        case TodoistTracker():
            return workspace_link(config).read()
        case LinearTracker():
            return None


def show(directory: WorkingDirectory, name: ConfigFileName) -> ExitCode:
    try:
        config = Configuration.resolved(directory, name)
        report = FlowReport.of(config, linked_task(config))
    except (InvalidConfigError, InvalidLinkError, MissingConfigError, OSError) as error:
        logger.error("%s", error)
        return ExitCode(1)
    _ = sys.stdout.write(f"{report.root}\n")
    return ExitCode(0)


def link(directory: WorkingDirectory, name: ConfigFileName, task: TaskId | None) -> ExitCode:
    try:
        config = Configuration.resolved(directory, name)
        match config.settings.issues:
            case TodoistTracker():
                linked = workspace_link(config).resolve(task)
            case LinearTracker():
                logger.error(
                    "%s tracks issues on Linear, where the workspace itself holds the link. Nothing to record.",
                    config.origin.root,
                )
                return ExitCode(1)
    except (
        InvalidConfigError,
        InvalidLinkError,
        MissingConfigError,
        MissingLinkError,
        OSError,
    ) as error:
        logger.error("%s", error)
        return ExitCode(1)
    _ = sys.stdout.write(f"{linked.root}\n")
    return ExitCode(0)
