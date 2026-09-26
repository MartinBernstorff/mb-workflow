import logging
import re
from pathlib import Path
from subprocess import CalledProcessError
from typing import TYPE_CHECKING

from mb_workflow.a_presentation.autolabel_report import log_outcome
from mb_workflow.a_presentation.console import ExitCode, Output, write
from mb_workflow.a_presentation.review_workspaces_report import (
    LoggingNarrator,
    log_review_workspaces_outcome,
)
from mb_workflow.b_core.a_features.autolabel import (
    AutolabelRequest,
    UnknownLabelError,
    label_eligible_issues,
)
from mb_workflow.b_core.a_features.edit_ticket import edit_ticket
from mb_workflow.b_core.a_features.finalize_review import NotFinalizableError, finalize
from mb_workflow.b_core.a_features.label import LabelRequest, UnlinkedWorktreeError, change_label
from mb_workflow.b_core.a_features.review_workspaces import create_workspaces
from mb_workflow.b_core.a_features.show_config import show_config
from mb_workflow.b_core.a_features.show_flow import show_flow
from mb_workflow.b_core.a_features.start import (
    PromptUndeliveredError,
    StartRequest,
    start_ticket,
)
from mb_workflow.b_core.a_features.transition import transition
from mb_workflow.b_core.a_features.view_ticket import view_ticket
from mb_workflow.b_core.c_secondary_ports.claims import ClaimRefusedError
from mb_workflow.b_core.c_secondary_ports.code_review import CodeReviewError
from mb_workflow.b_core.c_secondary_ports.run_lock import AlreadyRunningError
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTrackerError
from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManagerError
from mb_workflow.b_core.d_domain_model.cache import CacheDirectory
from mb_workflow.b_core.d_domain_model.config import (
    ConfigFileName,
    Configuration,
    InvalidConfigError,
    MissingConfigError,
    WorkingDirectory,
)
from mb_workflow.b_core.d_domain_model.flow import EventName, FlowError, StateNames, WorkflowChart
from mb_workflow.c_infrastructure.credentials import (
    CredentialsDirectory,
    InvalidCredentialsError,
    MissingCredentialsError,
    RepositorySlug,
)
from mb_workflow.c_infrastructure.flock import FlockRunLock, LockName, LockPath
from mb_workflow.c_infrastructure.github import GitHub
from mb_workflow.c_infrastructure.ledger_file import FileLedgerStore
from mb_workflow.c_infrastructure.linear import Linear, LinearApiKey
from mb_workflow.c_infrastructure.linear_claims import LinearClaims
from mb_workflow.c_infrastructure.orca import Orca
from mb_workflow.c_infrastructure.shell import ExistingDirectory, Shell
from mb_workflow.c_infrastructure.sleep import SleepingPause
from mb_workflow.c_infrastructure.workspace_board import BoardError, WorkspaceBoard

if TYPE_CHECKING:
    from collections.abc import Callable

    from mb_workflow.b_core.b_domain_services.flow_report import AsJson
    from mb_workflow.b_core.b_domain_services.flow_transition import Force
    from mb_workflow.b_core.d_domain_model.issue import CreatedAfter, IssueIdentifier
    from mb_workflow.b_core.d_domain_model.pull_request import MergedSince, ReviewRequest
    from mb_workflow.b_core.d_domain_model.ticket_edit import TicketEdit
    from mb_workflow.b_core.d_domain_model.workspace import WorkspaceStatus

logger = logging.getLogger(__name__)

# The failures a feature may raise. The console is the one place that turns them into a code,
# so every command below shares this set rather than repeating its own.
FAILURES = (
    AlreadyRunningError,
    BoardError,
    CalledProcessError,
    ClaimRefusedError,
    CodeReviewError,
    FlowError,
    InvalidConfigError,
    InvalidCredentialsError,
    MissingConfigError,
    MissingCredentialsError,
    NotFinalizableError,
    OSError,
    PromptUndeliveredError,
    TicketTrackerError,
    UnknownLabelError,
    UnlinkedWorktreeError,
    ValueError,
    WorkspaceManagerError,
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


def linear_key() -> LinearApiKey:
    path = CredentialsDirectory.of_user().path_for(RepositorySlug.of_origin(here()))
    return path.credentials().linear.api_key


def linear() -> Linear:
    return Linear.connected(linear_key())


def workspace_board(orca: Orca) -> WorkspaceBoard:
    return WorkspaceBoard.of_orca(orca, StateNames.initial_state(WorkflowChart))


@guarded
def review_workspaces(status: WorkspaceStatus, since: MergedSince, lock: LockName) -> ExitCode:
    shell = here()
    outcome = create_workspaces(
        review=GitHub(shell),
        manager=Orca(shell),
        lock=FlockRunLock(LockPath.of(lock)),
        narrator=LoggingNarrator(),
        status=status,
        since=since,
    )
    log_review_workspaces_outcome(outcome)
    return ExitCode.of(outcome.failed_any())


@guarded
def finalize_review(request: ReviewRequest, status: WorkspaceStatus) -> ExitCode:
    shell = here()
    finalize(GitHub(shell), Orca(shell), request, status)
    return ExitCode(0)


@guarded
def relabel(request: LabelRequest) -> ExitCode:
    change_label(Orca(here()), linear(), request)
    return ExitCode(0)


@guarded
def linear_autolabel(request: AutolabelRequest, window: CreatedAfter) -> ExitCode:
    outcome = label_eligible_issues(
        linear(), FileLedgerStore(CacheDirectory.of_user()), request, window
    )
    log_outcome(outcome)
    return ExitCode.of(outcome.failed_any())


@guarded
def ticket_start(
    request: StartRequest, directory: WorkingDirectory, name: ConfigFileName
) -> ExitCode:
    workspace = Configuration.resolved(directory, name).settings.workspace
    orca = Orca(here())
    key = linear_key()
    start_ticket(
        manager=orca,
        tracker=Linear.connected(key),
        claims=LinearClaims.connected(key),
        pause=SleepingPause(),
        board=workspace_board(orca),
        workspace=workspace,
        request=request,
    )
    return ExitCode(0)


@guarded
def ticket_view(issue: IssueIdentifier) -> ExitCode:
    write(Output(view_ticket(linear(), issue).root))
    return ExitCode(0)


@guarded
def ticket_edit(issue: IssueIdentifier, edit: TicketEdit) -> ExitCode:
    edit_ticket(linear(), issue, edit)
    write(Output(f"{issue.root}\n"))
    return ExitCode(0)


@guarded
def flow_config(directory: WorkingDirectory, name: ConfigFileName) -> ExitCode:
    write(Output(f"{show_config(directory, name).root}\n"))
    return ExitCode(0)


@guarded
def flow_show(as_json: AsJson) -> ExitCode:
    write(Output(show_flow(workspace_board(Orca(here())), as_json).root))
    return ExitCode(0)


@guarded
def flow_event(event: EventName, force: Force) -> ExitCode:
    logger.info("Moved to %s.", transition(workspace_board(Orca(here())), event, force).root)
    return ExitCode(0)
