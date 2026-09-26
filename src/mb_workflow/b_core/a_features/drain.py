import logging
from typing import TYPE_CHECKING

from mb_workflow.b_core.a_features.autolabel import DryRun
from mb_workflow.b_core.a_features.start import StartRequest, start_ticket
from mb_workflow.b_core.b_domain_services.pick_order import in_pick_order
from mb_workflow.b_core.c_secondary_ports.claims import (
    ClaimLostError,
    LabelledClaim,
    release_claim,
    require_claim_label,
)
from mb_workflow.b_core.d_domain_model.claim import ClaimHolder, HostName, SettleTime, TakeOver
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
from mb_workflow.b_core.d_domain_model.pool import PoolTickets
from mb_workflow.b_core.d_domain_model.workspace import Submit, TimeoutMs, WorktreeName
from mb_workflow.d_lib.models import Model

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.claims import ClaimRegistry, Pause
    from mb_workflow.b_core.c_secondary_ports.run_lock import RunLock
    from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.c_secondary_ports.tie_break import TieBreak
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManager
    from mb_workflow.b_core.d_domain_model.config import (
        ClaimSettings,
        PoolSettings,
        WorkspaceSettings,
    )

logger = logging.getLogger(__name__)


class DrainRequest(Model):
    dry_run: DryRun
    idle_timeout: TimeoutMs
    host: HostName
    settle: SettleTime

    @staticmethod
    def fake() -> DrainRequest:
        return DrainRequest(
            dry_run=DryRun(False),
            idle_timeout=TimeoutMs.fake(),
            host=HostName.fake(),
            settle=SettleTime.fake(),
        )

    def start_request(self, ticket: IssueIdentifier) -> StartRequest:
        return StartRequest(
            ticket=ticket,
            submit=Submit(True),
            idle_timeout=self.idle_timeout,
            host=self.host,
            take_over=TakeOver(False),
            settle=self.settle,
        )


class DrainOutcome(Model):
    ready: PoolTickets
    started: IssueIdentifier | None

    @staticmethod
    def fake() -> DrainOutcome:
        return DrainOutcome(ready=PoolTickets.fake(), started=IssueIdentifier.fake())


def drain_pool(
    *,
    tracker: TicketTracker,
    claims: ClaimRegistry,
    pause: Pause,
    manager: WorkspaceManager,
    board: WorkspaceStatusStore,
    lock: RunLock,
    tie_break: TieBreak,
    workspace: WorkspaceSettings,
    claim_settings: ClaimSettings,
    pool: PoolSettings,
    request: DrainRequest,
) -> DrainOutcome:
    with lock.held():
        require_claim_label(tracker, claim_settings.label)
        ready = in_pick_order(
            tracker.view_tickets(pool.view).ready(claim_settings.label), tie_break
        )
        if request.dry_run.root:
            return DrainOutcome(ready=ready, started=None)
        for ticket in ready.identifiers():
            try:
                start_ticket(
                    manager=manager,
                    tracker=tracker,
                    claims=claims,
                    pause=pause,
                    board=board,
                    workspace=workspace,
                    claim_settings=claim_settings,
                    request=request.start_request(ticket),
                )
            except ClaimLostError as error:
                logger.info("%s Trying the next ticket.", error)
                continue
            except Exception:
                release_claim(
                    claims,
                    tracker,
                    LabelledClaim(
                        ticket=ticket,
                        holder=ClaimHolder(
                            host=request.host, worktree=WorktreeName.of_issue(ticket)
                        ),
                        label=claim_settings.label,
                    ),
                )
                raise
            return DrainOutcome(ready=ready, started=ticket)
        return DrainOutcome(ready=ready, started=None)
