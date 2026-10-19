import logging
from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from mb_workflow.b_core.a_features.autolabel import DryRun, UnknownLabelError
from mb_workflow.b_core.a_features.start import StartRequest, TicketStart
from mb_workflow.b_core.b_domain_services.pick_order import PickOrder
from mb_workflow.b_core.c_secondary_ports.claims import Claiming, ClaimLostError
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import LabelCheck
from mb_workflow.b_core.d_domain_model.claim import HostName, Released, TakeOver
from mb_workflow.b_core.d_domain_model.flow import FlowError
from mb_workflow.b_core.d_domain_model.issue import LabelName, LabelNames
from mb_workflow.b_core.d_domain_model.pool import (
    Limit,
    Occupancy,
    PoolTicket,
    PoolTickets,
    Refusal,
    SkipLimits,
)
from mb_workflow.b_core.d_domain_model.workspace import Activate, Submit, TimeoutMs
from mb_workflow.d_lib.logging import Activity
from mb_workflow.d_lib.models import Model, Value

if TYPE_CHECKING:
    from mb_workflow.b_core.b_domain_services.flow_label_check import MissingFlowLabelsError
    from mb_workflow.b_core.c_secondary_ports.claims import (
        ClaimRefusedError,
        ClaimRegistry,
        UnknownClaimLabelError,
    )
    from mb_workflow.b_core.c_secondary_ports.run_lock import AlreadyRunningError, RunLock
    from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
        TicketTracker,
        TicketTrackerError,
    )
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import (
        WorkspaceManager,
        WorkspaceManagerError,
    )
    from mb_workflow.b_core.d_domain_model.config import (
        ClaimSettings,
        PoolSettings,
        WorkspaceSettings,
    )
    from mb_workflow.b_core.d_domain_model.flow import StateName
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
    from mb_workflow.b_core.d_domain_model.pool import Slot
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

    # The state is given only for a ticket without a flow state, which starts in it.
    def start_request(self, ticket: IssueIdentifier, state: StateName | None) -> StartRequest:
        return StartRequest(
            ticket=ticket,
            submit=Submit(True),
            idle_timeout=self.idle_timeout,
            host=self.host,
            take_over=TakeOver(False),
            activate=Activate(False),
            state=state,
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
    def of(
        ticket: PoolTicket, claim_label: LabelName, flow_labels: FlowLabels, skip_limits: SkipLimits
    ) -> Unready:
        return Unready(
            ticket=ticket, reason=Unready.reason_of(ticket, claim_label, flow_labels, skip_limits)
        )

    @staticmethod
    def reason_of(
        ticket: PoolTicket, claim_label: LabelName, flow_labels: FlowLabels, skip_limits: SkipLimits
    ) -> UnreadyReason:
        if ticket.issue.labels.matching(claim_label) is not None:
            return UnreadyReason("it is already claimed")
        match ticket.starting_state(flow_labels, skip_limits):
            case Err(error):
                return UnreadyReason(str(error))
            case Ok(state):
                if state is None:
                    return UnreadyReason("it has no flow state")
                return UnreadyReason(f"no agent works tickets in {state.root}")


# A ticket the skip-limits label started although the limits refused it.
class Override(Model):
    ticket: PoolTicket
    refusal: Refusal

    @staticmethod
    def fake() -> Override:
        return Override(ticket=PoolTicket.fake(), refusal=Refusal.fake())


class LossReason(Value[str]):
    @staticmethod
    def fake() -> LossReason:
        return LossReason("another host holds it")


# A ticket that was ready when listed but could not be started.
class Lost(Model):
    ticket: PoolTicket
    reason: LossReason

    @staticmethod
    def fake() -> Lost:
        return Lost(ticket=PoolTicket.fake(), reason=LossReason.fake())


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
    overridden: tuple[Override, ...] = ()
    lost: tuple[Lost, ...] = ()

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


# The labels a pool's config names, each of which must exist before a pass claims anything.
class PoolLabels(Model):
    claim: LabelName
    limited: LabelNames
    skip_limits: LabelName

    @staticmethod
    def fake() -> PoolLabels:
        return PoolLabels(
            claim=LabelName("claimed"),
            limited=LabelNames.fake(),
            skip_limits=LabelName("skip-limits"),
        )

    @staticmethod
    def of(claim_settings: ClaimSettings, pool: PoolSettings) -> PoolLabels:
        return PoolLabels(
            claim=claim_settings.label,
            limited=pool.limits.limited_labels(),
            skip_limits=pool.skip_limits_label,
        )


class Drain:
    # Checked before claiming, so a misspelt limit never lets a pass run uncapped.
    @staticmethod
    def require_limited_labels(
        known: LabelNames, limited: LabelNames
    ) -> Result[None, UnknownLabelError]:
        unknown = known.unmatched(limited)
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
        known: LabelNames, label: LabelName
    ) -> Result[None, UnknownLabelError]:
        return LabelCheck.require_known(
            known,
            label,
            UnknownLabelError(
                f"No label is named {label.root}. Create the label or change [pool] skip_limits_label."
            ),
        )

    # Lists the workspace's labels once and checks every pool label against that listing.
    @staticmethod
    def require_pool_labels(
        tracker: TicketTracker, labels: PoolLabels
    ) -> Result[None, TicketTrackerError | UnknownClaimLabelError | UnknownLabelError]:
        with Activity("Checking that the pool's labels exist").logged(logger):
            listed = tracker.workspace_labels()
        if isinstance(listed, Err):
            return listed
        known = listed.value
        checked = LabelCheck.require_known(
            known, labels.claim, Claiming.unknown_claim_label(labels.claim)
        )
        if isinstance(checked, Err):
            return checked
        checked = Drain.require_limited_labels(known, labels.limited)
        if isinstance(checked, Err):
            return checked
        return Drain.require_skip_limits_label(known, labels.skip_limits)

    # The view's tickets with their flow states, and the slots the tickets in progress fill.
    # The labels are checked first, so a misspelt limit never lets a pass run uncapped.
    # Labels an earlier pass found are not listed again, so a watch lists them only when they change.
    @staticmethod
    def read_pool(
        tracker: TicketTracker,
        claim_settings: ClaimSettings,
        flow_labels: FlowLabels,
        pool: PoolSettings,
        found_labels: PoolLabels | None,
    ) -> Result[
        tuple[PoolTickets, Occupancy],
        TicketTrackerError | UnknownClaimLabelError | UnknownLabelError | FlowError,
    ]:
        labels = PoolLabels.of(claim_settings, pool)
        if labels != found_labels:
            checked = Drain.require_pool_labels(tracker, labels)
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
        workspace: WorkspaceSettings,
        claim_settings: ClaimSettings,
        flow_labels: FlowLabels,
        statuses: TicketStatuses,
        pool: PoolSettings,
        found_labels: PoolLabels | None,
        request: DrainRequest,
    ) -> Result[
        DrainOutcome,
        AlreadyRunningError
        | FlowError
        | TicketTrackerError
        | UnknownClaimLabelError
        | ClaimRefusedError
        | UnknownLabelError
        | MissingFlowLabelsError
        | WorkspaceManagerError,
    ]:
        match lock.acquire():
            case Ok(held):
                with held:
                    return Drain.drain_holding_lock(
                        tracker=tracker,
                        claims=claims,
                        manager=manager,
                        board=board,
                        workspace=workspace,
                        claim_settings=claim_settings,
                        flow_labels=flow_labels,
                        statuses=statuses,
                        pool=pool,
                        found_labels=found_labels,
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
        workspace: WorkspaceSettings,
        claim_settings: ClaimSettings,
        flow_labels: FlowLabels,
        statuses: TicketStatuses,
        pool: PoolSettings,
        found_labels: PoolLabels | None,
        request: DrainRequest,
    ) -> Result[
        DrainOutcome,
        FlowError
        | TicketTrackerError
        | UnknownClaimLabelError
        | ClaimRefusedError
        | UnknownLabelError
        | MissingFlowLabelsError
        | WorkspaceManagerError,
    ]:
        with Activity("Draining the pool").logged(logger):
            read = Drain.read_pool(tracker, claim_settings, flow_labels, pool, found_labels)
            if isinstance(read, Err):
                return read
            listed, occupancy = read.value
            skip_limits = pool.skip_limits()
            unready = tuple(
                Unready.of(ticket, claim_settings.label, flow_labels, skip_limits)
                for ticket in listed.root
                if not ticket.ready(claim_settings.label, flow_labels, skip_limits).root
            )
            ready = PickOrder.ordered(
                listed.ready(claim_settings.label, flow_labels, skip_limits), pool.skip_limits_label
            )
            picked: list[PoolTicket] = []
            skipped: list[Skip] = []
            overridden: list[Override] = []
            lost: list[Lost] = []
            full: PoolFull | None = None
            for position, ticket in enumerate(ready.root):
                skips_limits = ticket.skips_limits(pool.skip_limits_label).root
                # Tickets that skip the limits sort first, so stopping here never passes one over.
                if not skips_limits and pool.limits.filled(occupancy).root:
                    full = PoolFull(
                        total=pool.limits.total, left=PoolTickets(ready.root[position:])
                    )
                    break
                found = ticket.slot(flow_labels, skip_limits)
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
                    overridden.append(Override(ticket=ticket, refusal=refusal))
                if request.dry_run.root:
                    picked.append(ticket)
                else:
                    attempted = Drain.take_ticket(
                        tracker=tracker,
                        claims=claims,
                        manager=manager,
                        board=board,
                        workspace=workspace,
                        claim_settings=claim_settings,
                        flow_labels=flow_labels,
                        statuses=statuses,
                        skip_limits_label=pool.skip_limits_label,
                        ticket=ticket,
                        slot=slot,
                        request=request,
                    )
                    if isinstance(attempted, Err):
                        return attempted
                    if attempted.value is None:
                        picked.append(ticket)
                    else:
                        lost.append(Lost(ticket=ticket, reason=attempted.value))
                # A ticket lost to another host is now in progress there, so it fills a slot too.
                occupancy = occupancy.with_slot(slot)
            return Ok(
                DrainOutcome(
                    ready=ready,
                    picked=PoolTickets(tuple(picked)),
                    skipped=tuple(skipped),
                    unready=unready,
                    full=full,
                    overridden=tuple(overridden),
                    lost=tuple(lost),
                )
            )

    @staticmethod
    def take_ticket(
        *,
        tracker: TicketTracker,
        claims: ClaimRegistry,
        manager: WorkspaceManager,
        board: WorkspaceStatusStore,
        workspace: WorkspaceSettings,
        claim_settings: ClaimSettings,
        flow_labels: FlowLabels,
        statuses: TicketStatuses,
        skip_limits_label: LabelName,
        ticket: PoolTicket,
        slot: Slot,
        request: DrainRequest,
    ) -> Result[
        LossReason | None,
        TicketTrackerError
        | UnknownClaimLabelError
        | ClaimRefusedError
        | MissingFlowLabelsError
        | WorkspaceManagerError,
    ]:
        ticket_summary = (
            f"{ticket.issue.identifier.root} ({ticket.priority.name}, {slot.state.root})"
        )
        unlabelled = ticket.flow_state(flow_labels).unwrap_or(None) is None
        with Activity(f"Taking {ticket_summary}").logged(logger):
            attempted = Drain.try_start_ticket(
                tracker=tracker,
                claims=claims,
                manager=manager,
                board=board,
                workspace=workspace,
                claim_settings=claim_settings,
                flow_labels=flow_labels,
                statuses=statuses,
                request=request.start_request(
                    ticket.issue.identifier, slot.state if unlabelled else None
                ),
            )
        if isinstance(attempted, Err) or attempted.value is not None:
            return attempted
        removed = Drain.remove_skip_limits_label(tracker, ticket, skip_limits_label)
        if isinstance(removed, Err):
            return removed
        return Ok(None)

    @staticmethod
    def remove_skip_limits_label(
        tracker: TicketTracker, ticket: PoolTicket, label: LabelName
    ) -> Result[None, TicketTrackerError]:
        if not ticket.skips_limits(label).root:
            return Ok(None)
        with Activity(f"Removing label {label.root} from {ticket.issue.identifier.root}").logged(
            logger
        ):
            return tracker.remove_label(ticket.issue.identifier, label)

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
    ) -> Result[
        LossReason | None,
        TicketTrackerError
        | UnknownClaimLabelError
        | ClaimRefusedError
        | MissingFlowLabelsError
        | WorkspaceManagerError,
    ]:
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
        match started:
            case Ok():
                return Ok(None)
            case Err(error):
                if isinstance(error, ClaimLostError):
                    return Ok(LossReason("another host holds it"))
                # The ticket was ready when listed, so a flow refusal here means its labels changed since.
                if isinstance(error, FlowError):
                    return Ok(LossReason(str(error)))
                return Err(error)
