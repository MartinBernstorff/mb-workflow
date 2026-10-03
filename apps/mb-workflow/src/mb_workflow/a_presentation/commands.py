import logging
import re
from pathlib import Path
from subprocess import CalledProcessError
from typing import TYPE_CHECKING, override

from safe_result import Err, Ok

from mb_workflow.a_presentation.autolabel_report import log_outcome
from mb_workflow.a_presentation.console import ExitCode, Output, write
from mb_workflow.a_presentation.drain_report import DrainReport, LoggingDrainNarrator
from mb_workflow.a_presentation.review_workspaces_report import (
    LoggingNarrator,
    log_review_workspaces_outcome,
)
from mb_workflow.b_core.a_features.autolabel import (
    AutolabelRequest,
    UnknownLabelError,
    label_eligible_issues,
)
from mb_workflow.b_core.a_features.create_ticket import create_ticket
from mb_workflow.b_core.a_features.drain import Drain, DrainRequest
from mb_workflow.b_core.a_features.drain_watch import (
    DrainSettings,
    DrainSettingsSource,
    DrainWatch,
    WatchRequest,
)
from mb_workflow.b_core.a_features.edit_ticket import TicketEditor
from mb_workflow.b_core.a_features.finalize_review import FinalizeReview
from mb_workflow.b_core.a_features.init_config import Overwrite, init_config
from mb_workflow.b_core.a_features.link import AlreadyLinkedError, LinkRequest, TicketLinking
from mb_workflow.b_core.a_features.review_workspaces import ReviewPrompt, create_workspaces
from mb_workflow.b_core.a_features.seed_labels import CoveredByWorkspace, seed_flow_labels
from mb_workflow.b_core.a_features.show_config import show_config
from mb_workflow.b_core.a_features.show_flow import show_flow
from mb_workflow.b_core.a_features.start import (
    PromptUndeliveredError,
    StartRequest,
    TicketStart,
)
from mb_workflow.b_core.a_features.teardown import TeardownRequest, teardown_worktree
from mb_workflow.b_core.a_features.transition import transition
from mb_workflow.b_core.a_features.unclaim import unclaim_ticket
from mb_workflow.b_core.a_features.view_ticket import view_ticket
from mb_workflow.b_core.b_domain_services.flow_label_check import MissingFlowLabelsError
from mb_workflow.b_core.c_secondary_ports.claims import ClaimRefusedError
from mb_workflow.b_core.c_secondary_ports.code_review import CodeReviewError
from mb_workflow.b_core.c_secondary_ports.run_lock import AlreadyRunningError
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTrackerError
from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManagerError
from mb_workflow.b_core.d_domain_model.cache import CacheDirectory
from mb_workflow.b_core.d_domain_model.config import (
    ClaimSettings,
    ConfigExistsError,
    ConfigFileName,
    Configuration,
    InvalidConfigError,
    MissingConfigError,
    WorkingDirectory,
)
from mb_workflow.b_core.d_domain_model.config_override import (
    InvalidOverrideError,
    ProjectOverride,
)
from mb_workflow.b_core.d_domain_model.config_template import ConfigTemplate
from mb_workflow.b_core.d_domain_model.flow import EventName, StateNames, WorkflowChart
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
from mb_workflow.b_core.d_domain_model.issue import LabelGroupName
from mb_workflow.b_core.d_domain_model.workspace import UnlinkedWorktreeError
from mb_workflow.c_infrastructure.credentials import (
    CredentialsDirectory,
    InvalidCredentialsError,
    MissingCredentialsError,
    RepositorySlug,
)
from mb_workflow.c_infrastructure.dev_environment import DevEnvironment
from mb_workflow.c_infrastructure.flock import FlockRunLock, LockName, LockPath
from mb_workflow.c_infrastructure.github import GitHub
from mb_workflow.c_infrastructure.lazy_linear import LazyLinear, LazyLinearClaims
from mb_workflow.c_infrastructure.ledger_file import FileLedgerStore
from mb_workflow.c_infrastructure.linear import Linear, LinearApiKey
from mb_workflow.c_infrastructure.linear_claims import LinearClaims
from mb_workflow.c_infrastructure.orca import Orca
from mb_workflow.c_infrastructure.project_override import override_of_origin
from mb_workflow.c_infrastructure.random_tie_break import RandomTieBreak
from mb_workflow.c_infrastructure.shell import ExistingDirectory, Shell
from mb_workflow.c_infrastructure.signal_stop import PollSeconds, SignalStop
from mb_workflow.c_infrastructure.workspace_board import BoardError, WorkspaceBoard

if TYPE_CHECKING:
    from collections.abc import Callable

    from mb_workflow.b_core.b_domain_services.flow_report import AsJson
    from mb_workflow.b_core.b_domain_services.flow_transition import Force
    from mb_workflow.b_core.d_domain_model.claim import HostName
    from mb_workflow.b_core.d_domain_model.issue import CreatedAfter, IssueIdentifier, TeamName
    from mb_workflow.b_core.d_domain_model.pull_request import MergedSince, ReviewRequest
    from mb_workflow.b_core.d_domain_model.ticket_draft import TicketDraft
    from mb_workflow.b_core.d_domain_model.ticket_edit import TicketEdit
    from mb_workflow.b_core.d_domain_model.workspace import WorkspaceStatus

logger = logging.getLogger(__name__)

# The failures a feature may raise. The console is the one place that turns them into a code,
# so every command below shares this set rather than repeating its own.
FAILURES = (
    AlreadyLinkedError,
    AlreadyRunningError,
    BoardError,
    CalledProcessError,
    ClaimRefusedError,
    CodeReviewError,
    ConfigExistsError,
    InvalidConfigError,
    InvalidCredentialsError,
    InvalidOverrideError,
    MissingConfigError,
    MissingCredentialsError,
    MissingFlowLabelsError,
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


# Err values from loading the configuration are raised here, so guarded reports them like any failure.
def user_override() -> ProjectOverride:
    return override_of_origin(CredentialsDirectory.of_user(), here()).unwrap()


def resolved_configuration(directory: WorkingDirectory, name: ConfigFileName) -> Configuration:
    return Configuration.resolved(directory, name, user_override()).unwrap()


def linear() -> Linear:
    return Linear.connected(linear_key())


def flow_labels_of_chart() -> FlowLabels:
    return FlowLabels.of_chart(WorkflowChart, LabelGroupName("flow"))


def workspace_board(orca: Orca) -> WorkspaceBoard:
    return WorkspaceBoard.of_orca(orca, StateNames.initial_state(WorkflowChart))


@guarded
def review_workspaces(
    status: WorkspaceStatus,
    since: MergedSince,
    lock: LockName,
    host: HostName,
    prompt: ReviewPrompt | None,
) -> ExitCode:
    # Review-workspaces predates the config file, so a repo without one still has its worktrees reconciled.
    try:
        claim_settings = resolved_configuration(
            WorkingDirectory(Path.cwd()), ConfigFileName.default()
        ).settings.claims
    except MissingConfigError:
        claim_settings = ClaimSettings()
    shell = here()
    outcome = create_workspaces(
        review=GitHub(shell),
        manager=Orca(shell),
        claims=LazyLinearClaims(linear_key),
        tracker=LazyLinear(linear_key),
        claim_settings=claim_settings,
        host=host,
        lock=FlockRunLock(LockPath.of(lock)),
        narrator=LoggingNarrator(),
        status=status,
        since=since,
        prompt=prompt,
    )
    log_review_workspaces_outcome(outcome)
    return ExitCode.of(outcome.failed_any())


@guarded
def finalize_review(request: ReviewRequest, status: WorkspaceStatus) -> ExitCode:
    shell = here()
    match FinalizeReview.finalize(GitHub(shell), Orca(shell), request, status):
        case Ok():
            return ExitCode(0)
        case Err(error):
            logger.error("%s", error)
            return ExitCode(1)


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
    settings = resolved_configuration(directory, name).settings
    orca = Orca(here())
    key = linear_key()
    match TicketStart.start_ticket(
        manager=orca,
        tracker=Linear.connected(key),
        claims=LinearClaims.connected(key),
        board=workspace_board(orca),
        workspace=settings.workspace,
        claim_settings=settings.claims,
        flow_labels=flow_labels_of_chart(),
        statuses=settings.ticket_statuses,
        request=request,
    ):
        case Ok():
            return ExitCode(0)
        case Err(error):
            logger.error("%s", error)
            return ExitCode(1)


@guarded
def ticket_link(
    request: LinkRequest, directory: WorkingDirectory, name: ConfigFileName
) -> ExitCode:
    settings = resolved_configuration(directory, name).settings
    orca = Orca(here())
    key = linear_key()
    match TicketLinking.link_ticket(
        manager=orca,
        tracker=Linear.connected(key),
        claims=LinearClaims.connected(key),
        board=workspace_board(orca),
        workspace=settings.workspace,
        claim_settings=settings.claims,
        flow_labels=flow_labels_of_chart(),
        request=request,
    ):
        case Ok():
            return ExitCode(0)
        case Err(error):
            logger.error("%s", error)
            return ExitCode(1)


@guarded
def drain(
    request: DrainRequest, lock: LockName, directory: WorkingDirectory, name: ConfigFileName
) -> ExitCode:
    settings = resolved_configuration(directory, name).settings
    pool = settings.required_pool()
    orca = Orca(here())
    key = linear_key()
    drained = Drain.drain_pool(
        tracker=Linear.connected(key),
        claims=LinearClaims.connected(key),
        manager=orca,
        board=workspace_board(orca),
        lock=FlockRunLock(LockPath.of_project(lock, settings.workspace.orca_project)),
        tie_break=RandomTieBreak(),
        workspace=settings.workspace,
        claim_settings=settings.claims,
        flow_labels=flow_labels_of_chart(),
        statuses=settings.ticket_statuses,
        pool=pool,
        request=request,
    )
    if isinstance(drained, Err):
        logger.error("%s", drained.error)
        return ExitCode(1)
    outcome = drained.value
    DrainReport.log_pass(outcome)
    if request.dry_run.root:
        write(DrainReport.pick_listing(outcome.picked, flow_labels_of_chart()))
    else:
        DrainReport.log_drain_outcome(outcome)
    return ExitCode(0)


class ConfiguredDrainSettings(DrainSettingsSource):
    def __init__(self, directory: WorkingDirectory, name: ConfigFileName) -> None:
        self._directory = directory
        self._name = name

    @override
    def current(self) -> DrainSettings:
        settings = resolved_configuration(self._directory, self._name).settings
        return DrainSettings(
            workspace=settings.workspace,
            claims=settings.claims,
            pool=settings.required_pool(),
            statuses=settings.ticket_statuses,
        )


@guarded
def drain_watch(
    request: WatchRequest, lock: LockName, directory: WorkingDirectory, name: ConfigFileName
) -> ExitCode:
    # The lock is taken once for the whole watch, so it uses the project configured at startup.
    project = resolved_configuration(directory, name).settings.workspace.orca_project
    orca = Orca(here())
    key = linear_key()
    with SignalStop.installed(PollSeconds(0.2)) as stop:
        DrainWatch.watch_pool(
            tracker=Linear.connected(key),
            claims=LinearClaims.connected(key),
            manager=orca,
            board=workspace_board(orca),
            lock=FlockRunLock(LockPath.of_project(lock, project)),
            tie_break=RandomTieBreak(),
            flow_labels=flow_labels_of_chart(),
            settings=ConfiguredDrainSettings(directory, name),
            stop=stop,
            narrator=LoggingDrainNarrator(),
            request=request,
        )
    return ExitCode(0)


@guarded
def teardown(
    request: TeardownRequest, directory: WorkingDirectory, name: ConfigFileName
) -> ExitCode:
    teardown_worktree(
        manager=Orca(here()),
        claims=LazyLinearClaims(linear_key),
        tracker=LazyLinear(linear_key),
        claim_settings=resolved_configuration(directory, name).settings.claims,
        request=request,
    )
    return ExitCode(0)


@guarded
def ticket_unclaim(
    ticket: IssueIdentifier, directory: WorkingDirectory, name: ConfigFileName
) -> ExitCode:
    unclaim_ticket(
        registry=LinearClaims.connected(linear_key()),
        tracker=linear(),
        claim_settings=resolved_configuration(directory, name).settings.claims,
        ticket=ticket,
    )
    return ExitCode(0)


@guarded
def ticket_view(issue: IssueIdentifier) -> ExitCode:
    write(Output(view_ticket(linear(), issue).root))
    return ExitCode(0)


@guarded
def ticket_edit(
    issue: IssueIdentifier, edit: TicketEdit, directory: WorkingDirectory, name: ConfigFileName
) -> ExitCode:
    statuses = resolved_configuration(directory, name).settings.ticket_statuses
    TicketEditor.apply_edit(linear(), issue, edit, flow_labels_of_chart(), statuses).unwrap()
    write(Output(f"{issue.root}\n"))
    return ExitCode(0)


@guarded
def ticket_create(
    draft: TicketDraft, directory: WorkingDirectory, name: ConfigFileName
) -> ExitCode:
    settings = resolved_configuration(directory, name).settings
    created = create_ticket(
        tracker=linear(),
        draft=draft,
        defaults=settings.ticket_defaults(),
        flow_labels=flow_labels_of_chart(),
        statuses=settings.ticket_statuses,
    ).unwrap()
    write(Output(f"{created.identifier.root} {created.url.root}\n"))
    return ExitCode(0)


@guarded
def init(directory: WorkingDirectory, name: ConfigFileName, overwrite: Overwrite) -> ExitCode:
    outcome = init_config(directory, name, ConfigTemplate.default(), overwrite)
    if outcome.shadowed is not None:
        logger.warning(
            "%s now takes precedence over %s in this directory.",
            outcome.written.root,
            outcome.shadowed.root,
        )
    write(Output(f"{outcome.written.root}\n"))
    return ExitCode(0)


@guarded
def config(directory: WorkingDirectory, name: ConfigFileName) -> ExitCode:
    write(Output(f"{show_config(directory, name, user_override()).unwrap().root}\n"))
    return ExitCode(0)


@guarded
def dev_setup() -> ExitCode:
    DevEnvironment(here()).set_up()
    return ExitCode(0)


@guarded
def flow_show(as_json: AsJson) -> ExitCode:
    write(Output(show_flow(workspace_board(Orca(here())), as_json).root))
    return ExitCode(0)


@guarded
def flow_event(
    event: EventName, force: Force, directory: WorkingDirectory, name: ConfigFileName
) -> ExitCode:
    orca = Orca(here())
    match transition(
        store=workspace_board(orca),
        tracker=linear(),
        manager=orca,
        wanted=flow_labels_of_chart(),
        statuses=resolved_configuration(directory, name).settings.ticket_statuses,
        event=event,
        force=force,
    ):
        case Ok(moved_to):
            logger.info("Moved to %s.", moved_to.root)
            return ExitCode(0)
        case Err(error):
            logger.error("%s", error)
            return ExitCode(1)


@guarded
def flow_seed_labels(team: TeamName) -> ExitCode:
    wanted = flow_labels_of_chart()
    seeded = seed_flow_labels(linear(), wanted, team)
    if isinstance(seeded, CoveredByWorkspace):
        logger.info(
            "The workspace's %s label group holds every flow label, so it covers %s."
            " Created nothing.",
            seeded.group.root,
            team.root,
        )
    elif seeded.created.root:
        logger.info(
            "Created %s in the %s label group of %s.",
            ", ".join(label.root for label in seeded.created.root),
            wanted.group.root,
            team.root,
        )
    else:
        logger.info(
            "The %s label group of %s already holds every flow label.",
            wanted.group.root,
            team.root,
        )
    if seeded.recolored.root:
        logger.info(
            "Recolored %s, so entry labels are yellow and the rest grey.",
            ", ".join(label.root for label in seeded.recolored.root),
        )
    return ExitCode(0)
