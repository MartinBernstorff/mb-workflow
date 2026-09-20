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
from mb_workflow.models import Value
from mb_workflow.shell import ExitCode

logger = logging.getLogger(__name__)


class FlowReport(Value[str]):
    @staticmethod
    def fake() -> FlowReport:
        return FlowReport.of(Configuration.fake())

    @staticmethod
    def of(config: Configuration) -> FlowReport:
        settings = config.settings
        lines = [f"tracker: {settings.issues.tracker}"]
        match settings.issues:
            case TodoistTracker():
                lines.append(f"project tag: {settings.issues.project_tag.root}")
            case LinearTracker():
                pass
        lines += [f"status store: {settings.status.store}", f"origin: {config.origin.root}"]
        return FlowReport("\n".join(lines))


def show(directory: WorkingDirectory, name: ConfigFileName) -> ExitCode:
    try:
        report = FlowReport.of(Configuration.resolved(directory, name))
    except (InvalidConfigError, MissingConfigError, OSError) as error:
        logger.error("%s", error)
        return ExitCode(1)
    _ = sys.stdout.write(f"{report.root}\n")
    return ExitCode(0)
