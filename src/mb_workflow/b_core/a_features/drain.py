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
from mb_workflow.b_core.d_domain_model.claim import ClaimHolder, HostName, Released, TakeOver
from mb_workflow.b_core.d_domain_model.pool import Occupancy, PoolTicket, PoolTickets
from mb_workflow.b_core.d_domain_model.workspace import Submit, TimeoutMs, WorktreeName
from mb_workflow.d_lib.models import Model, Value

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.claims import ClaimRegistry
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
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier

logger = logging.getLogger(__name__)


class DrainRequest(Model):
    dry_run: DryRun
    idle_timeout: TimeoutMs
    host: HostName

    @staticmethod
    def fake() -> DrainRequest:
        return DrainRequest(
            dry_run=DryRun(False),
            idle_timeout=TimeoutMs.fake(),
            host=HostName.fake(),
        )

    def start_request(self, ticket: IssueIdentifier) -> StartRequest:
        return StartRequest(
            ticket=ticket,
            submit=Submit(True),
            idle_timeout=self.idle_timeout,
            host=self.host,
            take_over=TakeOver(False),
        )


class DrainOutcome(Model):
    ready: PoolTickets
    picked: PoolTickets

    @staticmethod
    def fake() -> DrainOutcome:
        return DrainOutcome(ready=PoolTickets.fake(), picked=PoolTickets.fake())


def drain_pool(
    *,
    tracker: TicketTracker,
    claims: ClaimRegistry,
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
            tracker.unblocked_view_tickets(pool.view).ready(claim_settings.label), tie_break
        )
        occupancy = Occupancy.of(tracker.labelled_issues(claim_settings.label, Released.statuses()))
        picked: list[PoolTicket] = []
        for ticket in ready.root:
            if pool.limits.filled(occupancy).root:
                break
            if not pool.limits.admits(occupancy, ticket.issue.status).root:
                continue
            if (
                request.dry_run.root
                or try_start_ticket(
                    tracker=tracker,
                    claims=claims,
                    manager=manager,
                    board=board,
                    workspace=workspace,
                    claim_settings=claim_settings,
                    request=request.start_request(ticket.issue.identifier),
                ).root
            ):
                picked.append(ticket)
            # A ticket lost to another host is now in progress there, so it fills a slot too.
            occupancy = occupancy.with_ticket_in(ticket.issue.status)
        return DrainOutcome(ready=ready, picked=PoolTickets(tuple(picked)))


class Started(Value[bool]):
    @staticmethod
    def fake() -> Started:
        return Started(True)


def try_start_ticket(
    *,
    tracker: TicketTracker,
    claims: ClaimRegistry,
    manager: WorkspaceManager,
    board: WorkspaceStatusStore,
    workspace: WorkspaceSettings,
    claim_settings: ClaimSettings,
    request: StartRequest,
) -> Started:
    try:
        start_ticket(
            manager=manager,
            tracker=tracker,
            claims=claims,
            board=board,
            workspace=workspace,
            claim_settings=claim_settings,
            request=request,
        )
    except ClaimLostError:
        logger.info("Another host holds %s; trying the next ticket.", request.ticket.root)
        return Started(False)
    except Exception:
        release_claim(
            claims,
            tracker,
            LabelledClaim(
                ticket=request.ticket,
                holder=ClaimHolder(
                    host=request.host, worktree=WorktreeName.of_issue(request.ticket)
                ),
                label=claim_settings.label,
            ),
        )
        raise
    return Started(True)
