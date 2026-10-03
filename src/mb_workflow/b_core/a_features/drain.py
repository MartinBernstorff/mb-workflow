import logging
from typing import TYPE_CHECKING

from mb_workflow.b_core.a_features.autolabel import DryRun, UnknownLabelError
from mb_workflow.b_core.a_features.start import StartRequest, start_ticket
from mb_workflow.b_core.b_domain_services.pick_order import in_pick_order
from mb_workflow.b_core.c_secondary_ports.claims import (
    ClaimLostError,
    LabelledClaim,
    release_claim,
    require_claim_label,
)
from mb_workflow.b_core.d_domain_model.claim import ClaimHolder, HostName, Released, TakeOver
from mb_workflow.b_core.d_domain_model.pool import (
    Limit,
    Occupancy,
    PoolLimits,
    PoolTicket,
    PoolTickets,
    Refusal,
)
from mb_workflow.b_core.d_domain_model.workspace import Activate, Submit, TimeoutMs, WorktreeName
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
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier, LabelName
    from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses

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
            activate=Activate(False),
            state=None,
        )


class Skip(Model):
    ticket: PoolTicket
    refusal: Refusal

    @staticmethod
    def fake() -> Skip:
        return Skip(ticket=PoolTicket.fake(), refusal=Refusal.fake())


class UnreadyReason(Value[str]):
    @staticmethod
    def fake() -> UnreadyReason:
        return UnreadyReason("it is already claimed")


class Unready(Model):
    ticket: PoolTicket
    reason: UnreadyReason

    @staticmethod
    def fake() -> Unready:
        return Unready(ticket=PoolTicket.fake(), reason=UnreadyReason.fake())

    @staticmethod
    def of(ticket: PoolTicket, claim_label: LabelName, flow_labels: FlowLabels) -> Unready:
        return Unready(ticket=ticket, reason=Unready.reason_of(ticket, claim_label, flow_labels))

    @staticmethod
    def reason_of(
        ticket: PoolTicket, claim_label: LabelName, flow_labels: FlowLabels
    ) -> UnreadyReason:
        if ticket.issue.labels.matching(claim_label) is not None:
            return UnreadyReason("it is already claimed")
        state = ticket.flow_state(flow_labels)
        if state is None:
            return UnreadyReason("it has no flow state")
        return UnreadyReason(f"no agent works tickets in {state.root}")


# The pass stopped at the total, leaving these ready tickets unstarted.
class PoolFull(Model):
    total: Limit
    left: PoolTickets

    @staticmethod
    def fake() -> PoolFull:
        return PoolFull(total=Limit.fake(), left=PoolTickets.fake())


class Changed(Value[bool]):
    @staticmethod
    def fake() -> Changed:
        return Changed(True)


class DrainOutcome(Model):
    ready: PoolTickets
    picked: PoolTickets
    skipped: tuple[Skip, ...]
    unready: tuple[Unready, ...] = ()
    full: PoolFull | None = None

    @staticmethod
    def fake() -> DrainOutcome:
        return DrainOutcome(
            ready=PoolTickets.fake(), picked=PoolTickets.fake(), skipped=(Skip.fake(),)
        )

    # A pass that started a ticket counts as changed even when its sets match the last pass's.
    def changed_since(self, previous: DrainOutcome | None) -> Changed:
        return Changed(
            previous is None
            or bool(self.picked.root)
            or set(self.ready.identifiers()) != set(previous.ready.identifiers())
            or set(self.picked.identifiers()) != set(previous.picked.identifiers())
        )


# Checked before claiming, so a misspelt limit never lets a pass run uncapped.
def require_limited_labels(tracker: TicketTracker, limits: PoolLimits) -> None:
    unknown = tracker.workspace_labels().unmatched(limits.limited_labels())
    if unknown.root:
        listed = ", ".join(label.root for label in unknown.root)
        raise UnknownLabelError(
            f"No label is named {listed}. Create the label or change [pool.limits.labels]."
        )


def require_skip_limits_label(tracker: TicketTracker, label: LabelName) -> None:
    if tracker.workspace_labels().matching(label) is None:
        raise UnknownLabelError(
            f"No label is named {label.root}. Create the label or change [pool] skip_limits_label."
        )


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
    flow_labels: FlowLabels,
    statuses: TicketStatuses,
    pool: PoolSettings,
    request: DrainRequest,
) -> DrainOutcome:
    with lock.held():
        require_claim_label(tracker, claim_settings.label)
        require_limited_labels(tracker, pool.limits)
        require_skip_limits_label(tracker, pool.skip_limits_label)
        listed = tracker.unblocked_view_tickets(pool.view)
        unready = tuple(
            Unready.of(ticket, claim_settings.label, flow_labels)
            for ticket in listed.root
            if not ticket.ready(claim_settings.label, flow_labels).root
        )
        ready = in_pick_order(
            listed.ready(claim_settings.label, flow_labels), pool.skip_limits_label, tie_break
        )
        occupancy = Occupancy.of(
            tracker.labelled_issues(claim_settings.label, Released.types()), flow_labels
        )
        picked: list[PoolTicket] = []
        skipped: list[Skip] = []
        full: PoolFull | None = None
        for position, ticket in enumerate(ready.root):
            skips_limits = ticket.skips_limits(pool.skip_limits_label).root
            # Tickets that skip the limits sort first, so stopping here never passes one over.
            if not skips_limits and pool.limits.filled(occupancy).root:
                full = PoolFull(total=pool.limits.total, left=PoolTickets(ready.root[position:]))
                break
            slot = ticket.slot(flow_labels)
            if slot is None:
                skipped.append(Skip(ticket=ticket, refusal=Refusal("it has no flow state")))
                continue
            refusal = pool.limits.refusal(occupancy, slot)
            if refusal is not None:
                if not skips_limits:
                    skipped.append(Skip(ticket=ticket, refusal=refusal))
                    continue
                logger.info(
                    "%s is labelled %s, so it starts although %s.",
                    ticket.issue.identifier.root,
                    pool.skip_limits_label.root,
                    refusal.root,
                )
            logger.info(
                "%s %s (%s, %s).",
                "Would start" if request.dry_run.root else "Starting",
                ticket.issue.identifier.root,
                ticket.priority.name,
                slot.state.root,
            )
            if request.dry_run.root:
                picked.append(ticket)
            elif try_start_ticket(
                tracker=tracker,
                claims=claims,
                manager=manager,
                board=board,
                workspace=workspace,
                claim_settings=claim_settings,
                flow_labels=flow_labels,
                statuses=statuses,
                request=request.start_request(ticket.issue.identifier),
            ).root:
                picked.append(ticket)
                if skips_limits:
                    tracker.remove_label(ticket.issue.identifier, pool.skip_limits_label)
            # A ticket lost to another host is now in progress there, so it fills a slot too.
            occupancy = occupancy.with_slot(slot)
        return DrainOutcome(
            ready=ready,
            picked=PoolTickets(tuple(picked)),
            skipped=tuple(skipped),
            unready=unready,
            full=full,
        )


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
    flow_labels: FlowLabels,
    statuses: TicketStatuses,
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
            flow_labels=flow_labels,
            statuses=statuses,
            request=request,
        )
    except ClaimLostError:
        logger.info("Another host holds %s; trying the next ticket.", request.ticket.root)
        return Started(False)
    # BaseException too: a second stop signal exits mid-start, and must not strand the claim.
    except BaseException:
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
