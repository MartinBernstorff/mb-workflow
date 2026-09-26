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
    sweep,
)
from mb_workflow.b_core.a_features.finalize_review import NotFinalizableError, finalize
from mb_workflow.b_core.a_features.label import LabelRequest, UnlinkedWorktreeError, change_label
from mb_workflow.b_core.a_features.open_issue import (
    OpenRequest,
    PromptUndeliveredError,
    UnprefixedStateError,
    open_workspace,
)
from mb_workflow.b_core.a_features.review_workspaces import create_workspaces
from mb_workflow.b_core.a_features.show_config import show_config
from mb_workflow.b_core.a_features.show_flow import show_flow
from mb_workflow.b_core.a_features.transition import transition
from mb_workflow.b_core.a_features.view_ticket import view_ticket
from mb_workflow.b_core.b_domain_services.lock import AlreadyRunningError, LockName, LockPath
from mb_workflow.b_core.c_secondary_ports.issue_tracker import IssueTrackerError
from mb_workflow.b_core.d_domain_model.config import (
    ConfigFileName,
    InvalidConfigError,
    MissingConfigError,
    WorkingDirectory,
)
from mb_workflow.b_core.d_domain_model.flow import EventName, FlowError
from mb_workflow.c_infrastructure.credentials import (
    CredentialsDirectory,
    InvalidCredentialsError,
    MissingCredentialsError,
    RepositorySlug,
)
from mb_workflow.c_infrastructure.linear import Linear
from mb_workflow.c_infrastructure.orca import Orca, OrcaError, WorkspaceStatus
from mb_workflow.c_infrastructure.shell import ExistingDirectory, Shell
from mb_workflow.c_infrastructure.workspace_board import BoardError

if TYPE_CHECKING:
    from collections.abc import Callable

    from mb_workflow.b_core.b_domain_services.flow_report import AsJson
    from mb_workflow.b_core.b_domain_services.flow_transition import Force
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
    from mb_workflow.c_infrastructure.github import Lookback, ReviewRequest

logger = logging.getLogger(__name__)

# The failures a feature may raise. The console is the one place that turns them into a code,
# so every command below shares this set rather than repeating its own.
FAILURES = (
    AlreadyRunningError,
    BoardError,
    CalledProcessError,
    FlowError,
    InvalidConfigError,
    InvalidCredentialsError,
    IssueTrackerError,
    MissingConfigError,
    MissingCredentialsError,
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


def linear() -> Linear:
    path = CredentialsDirectory.of_user().path_for(RepositorySlug.of_origin(here()))
    return Linear.connected(path.credentials().linear.api_key)


@guarded
def review_workspaces(status: WorkspaceStatus, lookback: Lookback, lock: LockName) -> ExitCode:
    return ExitCode.of(create_workspaces(here(), status, lookback, LockPath.of(lock)).failed_any())


@guarded
def finalize_review(request: ReviewRequest, status: WorkspaceStatus) -> ExitCode:
    finalize(here(), request, status)
    return ExitCode(0)


@guarded
def relabel(request: LabelRequest) -> ExitCode:
    change_label(Orca(here()), linear(), request)
    return ExitCode(0)


@guarded
def linear_autolabel(request: AutolabelRequest, ledger: LedgerPath) -> ExitCode:
    return ExitCode.of(sweep(linear(), request, ledger).failed_any())


@guarded
def open_linear_issue(request: OpenRequest) -> ExitCode:
    open_workspace(Orca(here()), linear(), request)
    return ExitCode(0)


@guarded
def ticket_view(issue: IssueIdentifier) -> ExitCode:
    write(Output(view_ticket(linear(), issue).root))
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
