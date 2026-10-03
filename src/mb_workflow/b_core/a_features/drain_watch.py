import logging
from typing import TYPE_CHECKING, Protocol

from mb_workflow.b_core.a_features.autolabel import UnknownLabelError
from mb_workflow.b_core.a_features.drain import DrainRequest, drain_pool
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

# Retrying cannot fix these; only an edit to the config or the tracker's labels can.
CONFIG_ERRORS = (
    InvalidConfigError,
    InvalidOverrideError,
    MissingConfigError,
    UnknownClaimLabelError,
    UnknownLabelError,
)


class DrainSettings(Model):
    workspace: WorkspaceSettings
    claims: ClaimSettings
    pool: PoolSettings

    @staticmethod
    def fake() -> DrainSettings:
        return DrainSettings(
            workspace=WorkspaceSettings.fake(),
            claims=ClaimSettings.fake(),
            pool=PoolSettings.fake(),
        )


# Read once per pass, so a config edit applies from the next pass.
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
) -> None:
    previous: DrainOutcome | None = None
    while not stop.requested().root:
        try:
            current = settings.current()
            outcome = drain_pool(
                tracker=tracker,
                claims=claims,
                manager=manager,
                board=board,
                lock=lock,
                tie_break=tie_break,
                workspace=current.workspace,
                claim_settings=current.claims,
                flow_labels=flow_labels,
                pool=current.pool,
                request=request.drain,
            )
        except AlreadyRunningError as error:
            logger.info("Skipped this pass: %s.", error)
        except CONFIG_ERRORS:
            raise
        except Exception as error:
            logger.error(
                "The pass failed; retrying in %s seconds. %s", request.interval.root, error
            )
        else:
            narrator.passed(outcome, outcome.changed_since(previous))
            previous = outcome
        stop.wait(request.interval)
