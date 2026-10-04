import logging
from typing import TYPE_CHECKING, Protocol

from safe_result import Err, Ok, Result

from mb_workflow.b_core.a_features.autolabel import UnknownLabelError
from mb_workflow.b_core.a_features.drain import Drain, DrainRequest
from mb_workflow.b_core.c_secondary_ports.claims import UnknownClaimLabelError
from mb_workflow.b_core.c_secondary_ports.run_lock import AlreadyRunningError
from mb_workflow.b_core.d_domain_model.clock import IntervalSeconds
from mb_workflow.b_core.d_domain_model.config import (
    ClaimSettings,
    InvalidConfigError,
    MissingConfigError,
    PoolSettings,
    WorkspaceSettings,
)
from mb_workflow.b_core.d_domain_model.config_override import InvalidOverrideError
from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses
from mb_workflow.d_lib.models import Model

if TYPE_CHECKING:
    from mb_workflow.b_core.a_features.drain import Changed, DrainOutcome
    from mb_workflow.b_core.c_secondary_ports.claims import ClaimRegistry
    from mb_workflow.b_core.c_secondary_ports.run_lock import RunLock
    from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore
    from mb_workflow.b_core.c_secondary_ports.stop_signal import StopSignal
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.c_secondary_ports.tie_break import TieBreak
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManager
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels

logger = logging.getLogger(__name__)


class DrainSettings(Model):
    workspace: WorkspaceSettings
    claims: ClaimSettings
    pool: PoolSettings
    statuses: TicketStatuses

    @staticmethod
    def fake() -> DrainSettings:
        return DrainSettings(
            workspace=WorkspaceSettings.fake(),
            claims=ClaimSettings.fake(),
            pool=PoolSettings.fake(),
            statuses=TicketStatuses.fake(),
        )


class DrainSettingsSource(Protocol):
    def current(self) -> DrainSettings: ...


class DrainNarrator(Protocol):
    def passed(self, outcome: DrainOutcome, changed: Changed) -> None: ...


class WatchRequest(Model):
    drain: DrainRequest
    interval: IntervalSeconds

    @staticmethod
    def fake() -> WatchRequest:
        return WatchRequest(drain=DrainRequest.fake(), interval=IntervalSeconds.fake())


class DrainWatch:
    @staticmethod
    def config_errors() -> tuple[type[Exception], ...]:
        return (InvalidConfigError, InvalidOverrideError, MissingConfigError)

    @staticmethod
    def watch_pool(
        *,
        tracker: TicketTracker,
        claims: ClaimRegistry,
        manager: WorkspaceManager,
        board: WorkspaceStatusStore,
        lock: RunLock,
        tie_break: TieBreak,
        flow_labels: FlowLabels,
        settings: DrainSettingsSource,
        stop: StopSignal,
        narrator: DrainNarrator,
        request: WatchRequest,
    ) -> Result[None, UnknownClaimLabelError | UnknownLabelError]:
        previous: DrainOutcome | None = None
        while not stop.requested().root:
            try:
                current = settings.current()
                attempted = Drain.drain_pool(
                    tracker=tracker,
                    claims=claims,
                    manager=manager,
                    board=board,
                    lock=lock,
                    tie_break=tie_break,
                    workspace=current.workspace,
                    claim_settings=current.claims,
                    flow_labels=flow_labels,
                    statuses=current.statuses,
                    pool=current.pool,
                    request=request.drain,
                )
            except DrainWatch.config_errors():
                raise
            except Exception as error:
                DrainWatch.log_failed_pass(request, error)
            else:
                match attempted:
                    case Ok(outcome):
                        narrator.passed(outcome, outcome.changed_since(previous))
                        previous = outcome
                    case Err(AlreadyRunningError() as refusal):
                        logger.info("Skipped this pass: %s.", refusal)
                    case Err(UnknownClaimLabelError() | UnknownLabelError() as unfixable):
                        return Err(unfixable)
                    case Err(error):
                        DrainWatch.log_failed_pass(request, error)
            stop.wait(request.interval)
        return Ok(None)

    @staticmethod
    def log_failed_pass(request: WatchRequest, error: Exception) -> None:
        logger.error("The pass failed; retrying in %s seconds. %s", request.interval.root, error)
