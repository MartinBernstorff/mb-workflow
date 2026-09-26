import logging
import re
from pathlib import Path
from subprocess import CalledProcessError
from typing import TYPE_CHECKING

from mb_workflow.a_presentation.console import ExitCode, Output, write
from mb_workflow.b_core.a_features.autolabel import (
    AutolabelRequest,
    LedgerPath,
    UnknownLabelError,
    autolabel,
)
from mb_workflow.b_core.a_features.finalize_review import NotFinalizableError, finalize
from mb_workflow.b_core.a_features.label import LabelRequest, UnlinkedWorktreeError, change_label
from mb_workflow.b_core.a_features.open_issue import (
    OpenRequest,
    PromptUndeliveredError,
    UnprefixedStateError,
    open_issue,
)
from mb_workflow.b_core.a_features.review_workspaces import create_workspaces
from mb_workflow.b_core.a_features.show_config import show_config
from mb_workflow.b_core.a_features.show_flow import show_flow
from mb_workflow.b_core.a_features.transition import transition
from mb_workflow.b_core.b_domain_services.lock import AlreadyRunningError, LockName, LockPath
from mb_workflow.b_core.d_domain_model.config import (
    ConfigFileName,
    InvalidConfigError,
    MissingConfigError,
    WorkingDirectory,
)
from mb_workflow.b_core.d_domain_model.directory import ExistingDirectory
from mb_workflow.b_core.d_domain_model.flow import EventName, FlowError
from mb_workflow.b_core.d_domain_model.review import MissingReviewBodyError
from mb_workflow.c_infrastructure.board import BoardError
from mb_workflow.c_infrastructure.orca import OrcaError, WorkspaceStatus
from mb_workflow.c_infrastructure.shell import Shell

if TYPE_CHECKING:
    from collections.abc import Callable

    from mb_workflow.b_core.b_domain_services.flow_report import AsJson
    from mb_workflow.b_core.b_domain_services.flow_transition import Force
    from mb_workflow.b_core.d_domain_model.pull_request import Lookback
    from mb_workflow.b_core.d_domain_model.review import ReviewRequest

logger = logging.getLogger(__name__)

# The failures a feature may raise. The console is the one place that turns them into a code,
# so every command below shares this set rather than repeating its own.
FAILURES = (
    AlreadyRunningError,
    BoardError,
    CalledProcessError,
    FlowError,
    InvalidConfigError,
    MissingConfigError,
    MissingReviewBodyError,
    NotFinalizableError,
    OSError,
    OrcaError,
    PromptUndeliveredError,
    UnknownLabelError,
    UnlinkedWorktreeError,
    UnprefixedStateError,
    ValueError,
    re.error,
)


def guarded[**P](work: Callable[P, ExitCode]) -> Callable[P, ExitCode]:
    def guarding(*args: P.args, **kwargs: P.kwargs) -> ExitCode:
        try:
            return work(*args, **kwargs)
        except FileNotFoundError as error:
            logger.error("%s is not installed or not on PATH.", error.filename)
            return ExitCode(1)
        except FAILURES as error:
            logger.error("%s", error)
            return ExitCode(1)

    return guarding


def here() -> Shell:
    return Shell(ExistingDirectory(Path.cwd()))


@guarded
def review_workspaces(status: WorkspaceStatus, lookback: Lookback, lock: LockName) -> ExitCode:
    return ExitCode.of(create_workspaces(here(), status, lookback, LockPath.of(lock)).failed_any())


@guarded
def finalize_review(request: ReviewRequest, status: WorkspaceStatus) -> ExitCode:
    finalize(here(), request, status)
    return ExitCode(0)


@guarded
def relabel(request: LabelRequest) -> ExitCode:
    change_label(here(), request)
    return ExitCode(0)


@guarded
def linear_autolabel(request: AutolabelRequest, ledger: LedgerPath) -> ExitCode:
    return ExitCode.of(autolabel(here(), request, ledger).failed_any())


@guarded
def open_linear_issue(request: OpenRequest) -> ExitCode:
    open_issue(here(), request)
    return ExitCode(0)


@guarded
def flow_config(directory: WorkingDirectory, name: ConfigFileName) -> ExitCode:
    write(Output(f"{show_config(directory, name).root}\n"))
    return ExitCode(0)


@guarded
def flow_show(as_json: AsJson) -> ExitCode:
    write(Output(show_flow(here(), as_json).root))
    return ExitCode(0)


@guarded
def flow_event(event: EventName, force: Force) -> ExitCode:
    logger.info("Moved to %s.", transition(here(), event, force).root)
    return ExitCode(0)
