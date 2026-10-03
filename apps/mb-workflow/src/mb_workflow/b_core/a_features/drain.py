import logging
from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from mb_workflow.b_core.a_features.autolabel import DryRun, UnknownLabelError
from mb_workflow.b_core.a_features.start import StartRequest, TicketStart
from mb_workflow.b_core.b_domain_services.pick_order import in_pick_order
from mb_workflow.b_core.c_secondary_ports.claims import Claiming, ClaimLostError
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import LabelCheck
from mb_workflow.b_core.d_domain_model.claim import HostName, Released, TakeOver
from mb_workflow.b_core.d_domain_model.flow import FlowError
from mb_workflow.b_core.d_domain_model.pool import (
    Limit,
    Occupancy,
    PoolLimits,
    PoolTicket,
    PoolTickets,
    Refusal,
)
from mb_workflow.b_core.d_domain_model.workspace import Activate, Submit, TimeoutMs
from mb_workflow.d_lib.logging import Activity
from mb_workflow.d_lib.models import Model, Value

if TYPE_CHECKING:
    from mb_workflow.b_core.b_domain_services.flow_label_check import MissingFlowLabelsError
    from mb_workflow.b_core.c_secondary_ports.claims import ClaimRegistry, UnknownClaimLabelError
    from mb_workflow.b_core.c_secondary_ports.run_lock import AlreadyRunningError, RunLock
    from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
        TicketTracker,
        TicketTrackerError,
    )
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
        match ticket.flow_state(flow_labels):
            case Err(error):
                return UnreadyReason(str(error))
            case Ok(state):
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


class Drain:
    # Checked before claiming, so a misspelt limit never lets a pass run uncapped.
    @staticmethod
    def require_limited_labels(
        tracker: TicketTracker, limits: PoolLimits
    ) -> Result[None, TicketTrackerError | UnknownLabelError]:
        with Activity("Checking that the limited labels exist").logged(logger):
            known = tracker.workspace_labels()
        if isinstance(known, Err):
            return known
        unknown = known.value.unmatched(limits.limited_labels())
        if unknown.root:
            listed = ", ".join(label.root for label in unknown.root)
            return Err(
                UnknownLabelError(
                    f"No label is named {listed}. Create the label or change [pool.limits.labels]."
                )
            )
        return Ok(None)

    @staticmethod
    def require_skip_limits_label(
        tracker: TicketTracker, label: LabelName
    ) -> Result[None, TicketTrackerError | UnknownLabelError]:
        return LabelCheck.require_label(
            tracker,
            label,
            UnknownLabelError(
                f"No label is named {label.root}. Create the label or change [pool] skip_limits_label."
            ),
        )

    @staticmethod
    def require_pool_labels(
        tracker: TicketTracker, claim_settings: ClaimSettings, pool: PoolSettings
    ) -> Result[None, TicketTrackerError | UnknownClaimLabelError | UnknownLabelError]:
        checked = Claiming.require_claim_label(tracker, claim_settings.label)
        if isinstance(checked, Err):
            return checked
        checked = Drain.require_limited_labels(tracker, pool.limits)
        if isinstance(checked, Err):
            return checked
        return Drain.require_skip_limits_label(tracker, pool.skip_limits_label)

    # The view's tickets with their flow states, and the slots the tickets in progress fill.
    # The labels are checked first, so a misspelt limit never lets a pass run uncapped.
    @staticmethod
    def read_pool(
        tracker: TicketTracker,
        claim_settings: ClaimSettings,
        flow_labels: FlowLabels,
        pool: PoolSettings,
    ) -> Result[
        tuple[PoolTickets, Occupancy],
        TicketTrackerError | UnknownClaimLabelError | UnknownLabelError | FlowError,
    ]:
        checked = Drain.require_pool_labels(tracker, claim_settings, pool)
        if isinstance(checked, Err):
            return checked
        with Activity(f"Listing the tickets in view {pool.view.root}").logged(logger):
            found = tracker.unblocked_view_tickets(pool.view)
        if isinstance(found, Err):
            return found
        listed = found.value.with_flow_states_resolved(flow_labels)
        if isinstance(listed, Err):
            return listed
        with Activity(f"Listing the tickets labelled {claim_settings.label.root}").logged(logger):
            in_progress = tracker.labelled_issues(claim_settings.label, Released.types())
        if isinstance(in_progress, Err):
            return in_progress
        match Occupancy.of(in_progress.value, flow_labels):
            case Ok(occupancy):
                return Ok((listed.value, occupancy))
            case Err() as failed:
                return failed

    @staticmethod
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
    ) -> Result[
        DrainOutcome,
        AlreadyRunningError
        | FlowError
        | TicketTrackerError
        | UnknownClaimLabelError
        | UnknownLabelError
        | MissingFlowLabelsError,
    ]:
        match lock.acquire():
            case Ok(held):
                with held:
                    return Drain.drain_holding_lock(
                        tracker=tracker,
                        claims=claims,
                        manager=manager,
                        board=board,
                        tie_break=tie_break,
                        workspace=workspace,
                        claim_settings=claim_settings,
                        flow_labels=flow_labels,
                        statuses=statuses,
                        pool=pool,
                        request=request,
                    )
            case Err() as refused:
                return refused

    @staticmethod
    def drain_holding_lock(
        *,
        tracker: TicketTracker,
        claims: ClaimRegistry,
        manager: WorkspaceManager,
        board: WorkspaceStatusStore,
        tie_break: TieBreak,
        workspace: WorkspaceSettings,
        claim_settings: ClaimSettings,
        flow_labels: FlowLabels,
        statuses: TicketStatuses,
        pool: PoolSettings,
        request: DrainRequest,
    ) -> Result[
        DrainOutcome,
        FlowError
        | TicketTrackerError
        | UnknownClaimLabelError
        | UnknownLabelError
        | MissingFlowLabelsError,
    ]:
        with Activity("Draining the pool").logged(logger):
            read = Drain.read_pool(tracker, claim_settings, flow_labels, pool)
            if isinstance(read, Err):
                return read
            listed, occupancy = read.value
            unready = tuple(
                Unready.of(ticket, claim_settings.label, flow_labels)
                for ticket in listed.root
                if not ticket.ready(claim_settings.label, flow_labels).root
            )
            ready = in_pick_order(
                listed.ready(claim_settings.label, flow_labels), pool.skip_limits_label, tie_break
            )
            picked: list[PoolTicket] = []
            skipped: list[Skip] = []
            full: PoolFull | None = None
            for position, ticket in enumerate(ready.root):
                skips_limits = ticket.skips_limits(pool.skip_limits_label).root
                # Tickets that skip the limits sort first, so stopping here never passes one over.
                if not skips_limits and pool.limits.filled(occupancy).root:
                    full = PoolFull(
                        total=pool.limits.total, left=PoolTickets(ready.root[position:])
                    )
                    break
                found = ticket.slot(flow_labels)
                if isinstance(found, Err):
                    return found
                slot = found.value
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
                ticket_summary = (
                    f"{ticket.issue.identifier.root} ({ticket.priority.name}, {slot.state.root})"
                )
                if request.dry_run.root:
                    logger.info("Would start %s.", ticket_summary)
                    picked.append(ticket)
                else:
                    with Activity(f"Taking {ticket_summary}").logged(logger):
                        started = Drain.try_start_ticket(
                            tracker=tracker,
                            claims=claims,
                            manager=manager,
                            board=board,
                            workspace=workspace,
                            claim_settings=claim_settings,
                            flow_labels=flow_labels,
                            statuses=statuses,
                            request=request.start_request(ticket.issue.identifier),
                        )
                    if isinstance(started, Err):
                        return started
                    if started.value.root:
                        picked.append(ticket)
                        if skips_limits:
                            with Activity(
                                f"Removing label {pool.skip_limits_label.root}"
                                f" from {ticket.issue.identifier.root}"
                            ).logged(logger):
                                tracker.remove_label(
                                    ticket.issue.identifier, pool.skip_limits_label
                                )
                # A ticket lost to another host is now in progress there, so it fills a slot too.
                occupancy = occupancy.with_slot(slot)
            return Ok(
                DrainOutcome(
                    ready=ready,
                    picked=PoolTickets(tuple(picked)),
                    skipped=tuple(skipped),
                    unready=unready,
                    full=full,
                )
            )

    @staticmethod
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
    ) -> Result[Started, TicketTrackerError | UnknownClaimLabelError | MissingFlowLabelsError]:
        try:
            started = TicketStart.start_ticket(
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
            return Ok(Started(False))
        match started:
            case Ok():
                return Ok(Started(True))
            case Err(error):
                # The ticket was ready when listed, so a flow refusal here means its labels changed since.
                if isinstance(error, FlowError):
                    logger.warning("Not starting %s: %s", request.ticket.root, error)
                    return Ok(Started(False))
                return Err(error)


class Started(Value[bool]):
    @staticmethod
    def fake() -> Started:
        return Started(True)
