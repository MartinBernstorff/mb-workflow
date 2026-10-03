import logging
import re
from typing import override

import pytest

from mb_workflow.b_core.a_features.autolabel import DryRun, UnknownLabelError
from mb_workflow.b_core.a_features.drain import (
    Changed,
    Drain,
    DrainOutcome,
    DrainRequest,
    UnreadyReason,
)
from mb_workflow.b_core.c_secondary_ports.claims import (
    FakeClaimRegistry,
    UnknownClaimLabelError,
)
from mb_workflow.b_core.c_secondary_ports.run_lock import AlreadyRunningError, FakeRunLock
from mb_workflow.b_core.c_secondary_ports.status import FakeStatusStore
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import FakeTicketTracker, TrackedIssue
from mb_workflow.b_core.c_secondary_ports.tie_break import ReversingTieBreak
from mb_workflow.b_core.c_secondary_ports.workspace_manager import (
    FakeWorkspaceManager,
    WorkspaceManagerError,
)
from mb_workflow.b_core.d_domain_model.claim import ClaimHolder, ClaimId, HostName
from mb_workflow.b_core.d_domain_model.config import ClaimSettings, PoolSettings, WorkspaceSettings
from mb_workflow.b_core.d_domain_model.flow import StateName, StateNames, WorkflowChart
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
from mb_workflow.b_core.d_domain_model.issue import (
    Issue,
    IssueIdentifier,
    IssueStatus,
    IssueStatuses,
    IssueStatusName,
    LabelName,
    LabelNames,
    StatusType,
)
from mb_workflow.b_core.d_domain_model.pool import (
    Limit,
    PoolLimits,
    PoolTicket,
    PoolTickets,
    Priority,
    Refusal,
)
from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses
from mb_workflow.b_core.d_domain_model.workspace import (
    Activate,
    AgentName,
    OpenedWorktree,
    ProjectSelector,
    TerminalText,
    WorkspaceStatus,
    WorkspaceStatuses,
    WorktreeName,
    WorktreePath,
    Worktrees,
)


def pooled(
    identifier: IssueIdentifier,
    priority: Priority,
    state: StateName | None = StateName("Specced"),
    labels: LabelNames = LabelNames(()),
    status: IssueStatusName = IssueStatusName("In Progress"),
) -> TrackedIssue:
    flow = () if state is None else (LabelName(state.root),)
    return TrackedIssue.fake().model_copy(
        update={
            "issue": Issue.fake().model_copy(
                update={
                    "identifier": identifier,
                    "status": status,
                    "labels": LabelNames((*flow, *labels.root)),
                }
            ),
            "priority": priority,
        }
    )


def in_progress(
    identifier: IssueIdentifier,
    state: StateName,
    status: IssueStatusName = IssueStatusName("In Progress"),
    labels: LabelNames = LabelNames(()),
) -> TrackedIssue:
    return pooled(
        identifier,
        Priority.medium,
        state=state,
        labels=LabelNames((LabelName("claimed"), *labels.root)),
        status=status,
    )


def statuses_in_flight(*closing: IssueStatus) -> IssueStatuses:
    return IssueStatuses(
        (IssueStatus(name=IssueStatusName("In Progress"), type=StatusType.started), *closing)
    )


def pool_of(
    *tickets: TrackedIssue,
    labels: LabelNames | None = None,
    elsewhere: tuple[TrackedIssue, ...] = (),
    closing: tuple[IssueStatus, ...] = (),
    kind: type[FakeTicketTracker] = FakeTicketTracker,
) -> FakeTicketTracker:
    return kind(
        LabelNames((LabelName("claimed"), skip_limits().root[0], *FlowLabels.fake().labels.root))
        if labels is None
        else labels,
        (*tickets, *elsewhere),
        statuses=statuses_in_flight(*closing),
        views={PoolSettings.fake().view: tuple(ticket.issue.identifier for ticket in tickets)},
        groups={FlowLabels.fake().group: FlowLabels.fake().labels},
    )


def skip_limits() -> LabelNames:
    return LabelNames((PoolSettings.fake().skip_limits_label,))


def refactors() -> LabelNames:
    return LabelNames((LabelName("refactor"),))


def pool_capping_refactors_at(limit: Limit) -> PoolSettings:
    return PoolSettings.fake().model_copy(
        update={"limits": PoolLimits(labels={LabelName("refactor"): limit})}
    )


def labels_with_refactor() -> LabelNames:
    return LabelNames(
        (
            LabelName("claimed"),
            LabelName("Refactor"),
            *skip_limits().root,
            *FlowLabels.fake().labels.root,
        )
    )


def pool_with_total(total: Limit) -> PoolSettings:
    return PoolSettings.fake().model_copy(
        update={"limits": PoolLimits().model_copy(update={"total": total})}
    )


def picked(outcome: DrainOutcome) -> tuple[IssueIdentifier, ...]:
    return outcome.picked.identifiers()


def standard_pool(kind: type[FakeTicketTracker] = FakeTicketTracker) -> FakeTicketTracker:
    return pool_of(
        pooled(IssueIdentifier("MB-1"), Priority.low),
        pooled(IssueIdentifier("MB-2"), Priority.high),
        pooled(IssueIdentifier("MB-3"), Priority.high, state=StateName("QA")),
        kind=kind,
    )


def fake_board() -> FakeStatusStore:
    return FakeStatusStore(StateName.fake())


def fake_manager(project: ProjectSelector = ProjectSelector.fake()) -> FakeWorkspaceManager:
    statuses = WorkspaceStatuses(
        tuple(fake_board().status_for(state) for state in StateNames.of_chart(WorkflowChart).root)
    )
    return FakeWorkspaceManager(Worktrees.fake(), WorktreePath.fake(), statuses, project=project)


def holder_of(ticket: IssueIdentifier) -> ClaimHolder:
    return ClaimHolder(host=DrainRequest.fake().host, worktree=WorktreeName.of_issue(ticket))


def rival() -> ClaimHolder:
    return ClaimHolder(host=HostName("bob-mbp.local"), worktree=WorktreeName("MB-2"))


def holders(claims: FakeClaimRegistry, ticket: IssueIdentifier) -> tuple[ClaimHolder, ...]:
    return tuple(claim.holder for claim in claims.claims(ticket).root)


def opened_issues(manager: FakeWorkspaceManager) -> tuple[IssueIdentifier | None, ...]:
    return tuple(
        worktree.issue for worktree in manager.worktrees().without(WorktreePath.fake()).root
    )


# Posts a rival's claim just before ours on one ticket, as if another host won the race to it.
class RacedRegistry(FakeClaimRegistry):
    def __init__(self, contested: IssueIdentifier) -> None:
        super().__init__()
        self._contested = contested

    @override
    def post(self, ticket: IssueIdentifier, holder: ClaimHolder) -> ClaimId:
        if ticket == self._contested and not self.claims(ticket).root:
            _ = super().post(ticket, rival())
        return super().post(ticket, holder)


def draining(
    tracker: FakeTicketTracker,
    *,
    manager: FakeWorkspaceManager | None = None,
    claims: FakeClaimRegistry | None = None,
    lock: FakeRunLock | None = None,
    pool: PoolSettings | None = None,
    request: DrainRequest | None = None,
) -> DrainOutcome:
    return Drain.drain_pool(
        tracker=tracker,
        claims=claims or FakeClaimRegistry(),
        manager=manager or fake_manager(),
        board=fake_board(),
        lock=lock or FakeRunLock(),
        tie_break=ReversingTieBreak(),
        workspace=WorkspaceSettings.fake(),
        claim_settings=ClaimSettings(label=LabelName("claimed")),
        flow_labels=FlowLabels.fake(),
        statuses=TicketStatuses.fake(),
        pool=pool or PoolSettings.fake(),
        request=request or DrainRequest.fake(),
    )


def test_starts_the_top_ready_ticket_and_submits_its_prompt() -> None:
    manager = fake_manager()
    claims = FakeClaimRegistry()
    outcome = draining(
        standard_pool(), manager=manager, claims=claims, pool=pool_with_total(Limit(1))
    )
    assert picked(outcome) == (IssueIdentifier("MB-2"),)
    assert holders(claims, IssueIdentifier("MB-2")) == (holder_of(IssueIdentifier("MB-2")),)
    assert opened_issues(manager) == (IssueIdentifier("MB-2"),)
    assert manager.submitted_texts() == (TerminalText("/implement MB-2"),)


def test_started_tickets_open_in_the_background() -> None:
    manager = fake_manager()
    _ = draining(standard_pool(), manager=manager)
    assert opened_issues(manager)
    assert manager.activated() == ()


def test_starts_every_ready_ticket_in_pick_order_while_the_total_allows() -> None:
    manager = fake_manager()
    outcome = draining(standard_pool(), manager=manager)
    assert picked(outcome) == (IssueIdentifier("MB-2"), IssueIdentifier("MB-1"))
    assert opened_issues(manager) == (IssueIdentifier("MB-2"), IssueIdentifier("MB-1"))


def test_the_pass_stops_once_the_total_is_reached() -> None:
    claims = FakeClaimRegistry()
    _ = draining(standard_pool(), claims=claims, pool=pool_with_total(Limit(1)))
    assert holders(claims, IssueIdentifier("MB-1")) == ()


def test_labelled_tickets_in_progress_count_toward_the_total() -> None:
    tracker = pool_of(
        pooled(IssueIdentifier("MB-1"), Priority.low),
        pooled(IssueIdentifier("MB-2"), Priority.high),
        elsewhere=(
            in_progress(IssueIdentifier("MB-10"), StateName("Implementing")),
            in_progress(IssueIdentifier("MB-11"), StateName("QA")),
            in_progress(IssueIdentifier("MB-12"), StateName("Review")),
        ),
    )
    assert picked(draining(tracker)) == (IssueIdentifier("MB-2"),)


@pytest.mark.parametrize(
    "closing",
    [
        IssueStatus(name=IssueStatusName("Shipped"), type=StatusType.completed),
        IssueStatus(name=IssueStatusName("Won't do"), type=StatusType.canceled),
    ],
)
def test_labelled_tickets_that_are_closed_do_not_count(closing: IssueStatus) -> None:
    tracker = pool_of(
        pooled(IssueIdentifier("MB-1"), Priority.low),
        elsewhere=(in_progress(IssueIdentifier("MB-10"), StateName("QA"), closing.name),),
        closing=(closing,),
    )
    assert picked(draining(tracker, pool=pool_with_total(Limit(1)))) == (IssueIdentifier("MB-1"),)


def test_unlabelled_tickets_do_not_count() -> None:
    tracker = pool_of(
        pooled(IssueIdentifier("MB-1"), Priority.low),
        elsewhere=(pooled(IssueIdentifier("MB-10"), Priority.low, state=StateName("QA")),),
    )
    assert picked(draining(tracker, pool=pool_with_total(Limit(1)))) == (IssueIdentifier("MB-1"),)


def test_a_ticket_whose_state_is_full_is_skipped_for_the_next() -> None:
    tracker = pool_of(
        pooled(IssueIdentifier("MB-1"), Priority.low),
        pooled(IssueIdentifier("MB-2"), Priority.high, state=StateName("Grilling")),
        elsewhere=(in_progress(IssueIdentifier("MB-10"), StateName("Grilling")),),
    )
    assert picked(draining(tracker)) == (IssueIdentifier("MB-1"),)


def test_a_ticket_started_in_the_pass_fills_its_state() -> None:
    tracker = pool_of(
        pooled(IssueIdentifier("MB-1"), Priority.low, state=StateName("Grilling")),
        pooled(IssueIdentifier("MB-2"), Priority.high, state=StateName("Grilling")),
    )
    assert picked(draining(tracker)) == (IssueIdentifier("MB-2"),)


def test_a_claimed_ticket_without_a_flow_label_does_not_count_toward_the_limits() -> None:
    tracker = pool_of(
        pooled(IssueIdentifier("MB-2"), Priority.high, state=StateName("Grilling")),
        elsewhere=(
            pooled(
                IssueIdentifier("MB-10"),
                Priority.medium,
                state=None,
                labels=LabelNames((LabelName("claimed"),)),
            ),
        ),
    )
    assert picked(draining(tracker, pool=pool_with_total(Limit(1)))) == (IssueIdentifier("MB-2"),)


def test_a_ticket_carrying_the_claim_label_is_passed_over() -> None:
    tracker = pool_of(
        pooled(IssueIdentifier("MB-1"), Priority.low),
        pooled(IssueIdentifier("MB-2"), Priority.high, labels=LabelNames((LabelName("claimed"),))),
    )
    assert picked(draining(tracker)) == (IssueIdentifier("MB-1"),)


def test_a_ticket_another_host_wins_is_passed_over_for_the_next() -> None:
    manager = fake_manager()
    claims = RacedRegistry(IssueIdentifier("MB-2"))
    outcome = draining(standard_pool(), manager=manager, claims=claims)
    assert picked(outcome) == (IssueIdentifier("MB-1"),)
    assert holders(claims, IssueIdentifier("MB-2")) == (rival(),)
    assert opened_issues(manager) == (IssueIdentifier("MB-1"),)


def test_a_ticket_another_host_wins_counts_toward_the_total() -> None:
    claims = RacedRegistry(IssueIdentifier("MB-2"))
    outcome = draining(standard_pool(), claims=claims, pool=pool_with_total(Limit(1)))
    assert picked(outcome) == ()
    assert holders(claims, IssueIdentifier("MB-1")) == ()


def test_a_start_that_fails_after_claiming_releases_the_claim() -> None:
    tracker = standard_pool()
    claims = FakeClaimRegistry()
    elsewhere = fake_manager(ProjectSelector("github:other/project"))
    with pytest.raises(WorkspaceManagerError):
        _ = draining(tracker, manager=elsewhere, claims=claims)
    assert holders(claims, IssueIdentifier("MB-2")) == ()
    assert tracker.read_issue(IssueIdentifier("MB-2")).labels == LabelNames((LabelName("Specced"),))


# Raises as a second stop signal would, after the workspace call begins.
class InterruptedManager(FakeWorkspaceManager):
    @override
    def create_for_issue(
        self,
        project: ProjectSelector,
        name: WorktreeName,
        issue: IssueIdentifier | None,
        agent: AgentName | None,
        status: WorkspaceStatus | None,
        *,
        activate: Activate,
    ) -> OpenedWorktree:
        raise SystemExit(143)


def test_a_start_interrupted_by_a_second_stop_signal_releases_the_claim() -> None:
    claims = FakeClaimRegistry()
    manager = InterruptedManager(
        Worktrees.fake(), WorktreePath.fake(), WorkspaceStatuses(()), project=ProjectSelector.fake()
    )
    with pytest.raises(SystemExit):
        _ = draining(standard_pool(), manager=manager, claims=claims)
    assert holders(claims, IssueIdentifier("MB-2")) == ()


def test_a_start_that_fails_tries_no_other_ticket() -> None:
    claims = FakeClaimRegistry()
    with pytest.raises(WorkspaceManagerError):
        _ = draining(
            standard_pool(),
            manager=fake_manager(ProjectSelector("github:other/project")),
            claims=claims,
        )
    assert holders(claims, IssueIdentifier("MB-1")) == ()


def test_a_claim_label_the_tracker_lacks_refuses_the_pass() -> None:
    tracker = pool_of(pooled(IssueIdentifier("MB-1"), Priority.low), labels=LabelNames(()))
    claims = FakeClaimRegistry()
    with pytest.raises(UnknownClaimLabelError, match="claimed"):
        _ = draining(tracker, claims=claims)
    assert holders(claims, IssueIdentifier("MB-1")) == ()


def test_a_dry_run_lists_the_tickets_the_limits_allow_and_starts_nothing() -> None:
    manager = fake_manager()
    claims = FakeClaimRegistry()
    tracker = pool_of(
        pooled(IssueIdentifier("MB-1"), Priority.low),
        pooled(IssueIdentifier("MB-2"), Priority.high, state=StateName("Grilling")),
        pooled(IssueIdentifier("MB-3"), Priority.high, state=StateName("QA")),
        pooled(IssueIdentifier("MB-4"), Priority.high),
        pooled(IssueIdentifier("MB-5"), Priority.no_priority),
        elsewhere=(
            in_progress(IssueIdentifier("MB-10"), StateName("Grilling")),
            in_progress(IssueIdentifier("MB-11"), StateName("QA")),
        ),
    )
    dry = DrainRequest.fake().model_copy(update={"dry_run": DryRun(True)})
    outcome = draining(tracker, manager=manager, claims=claims, request=dry)
    assert picked(outcome) == (IssueIdentifier("MB-4"), IssueIdentifier("MB-1"))
    assert manager.worktrees() == Worktrees.fake()
    assert holders(claims, IssueIdentifier("MB-4")) == ()


def test_a_pool_with_no_ready_ticket_starts_nothing() -> None:
    manager = fake_manager()
    outcome = draining(
        pool_of(pooled(IssueIdentifier("MB-3"), Priority.high, state=StateName("QA"))),
        manager=manager,
    )
    assert outcome.ready == PoolTickets(())
    assert outcome.picked == PoolTickets(())
    assert outcome.skipped == ()
    assert outcome.full is None
    assert manager.worktrees() == Worktrees.fake()


def test_a_pass_is_refused_while_another_holds_the_lock() -> None:
    lock = FakeRunLock()
    claims = FakeClaimRegistry()
    with lock.held(), pytest.raises(AlreadyRunningError):
        _ = draining(standard_pool(), claims=claims, lock=lock)
    assert holders(claims, IssueIdentifier("MB-2")) == ()


def test_a_ticket_labelled_skip_limits_starts_past_the_total() -> None:
    tracker = pool_of(
        pooled(IssueIdentifier("MB-1"), Priority.urgent),
        pooled(IssueIdentifier("MB-2"), Priority.low, labels=skip_limits()),
        pooled(IssueIdentifier("MB-3"), Priority.low, labels=skip_limits()),
    )
    assert picked(draining(tracker, pool=pool_with_total(Limit(1)))) == (
        IssueIdentifier("MB-3"),
        IssueIdentifier("MB-2"),
    )


def test_a_ticket_labelled_skip_limits_starts_in_a_full_state() -> None:
    tracker = pool_of(
        pooled(
            IssueIdentifier("MB-2"), Priority.low, state=StateName("Grilling"), labels=skip_limits()
        ),
        elsewhere=(in_progress(IssueIdentifier("MB-10"), StateName("Grilling")),),
    )
    assert picked(draining(tracker)) == (IssueIdentifier("MB-2"),)


def test_tickets_labelled_skip_limits_count_toward_the_limits_of_the_rest() -> None:
    tracker = pool_of(
        pooled(IssueIdentifier("MB-1"), Priority.high),
        pooled(IssueIdentifier("MB-2"), Priority.low, labels=skip_limits()),
    )
    assert picked(draining(tracker, pool=pool_with_total(Limit(1)))) == (IssueIdentifier("MB-2"),)


def test_a_started_ticket_loses_its_skip_limits_label() -> None:
    tracker = pool_of(pooled(IssueIdentifier("MB-2"), Priority.low, labels=skip_limits()))
    _ = draining(tracker)
    assert (
        tracker.read_issue(IssueIdentifier("MB-2")).labels.matching(
            PoolSettings.fake().skip_limits_label
        )
        is None
    )


def test_a_dry_run_keeps_the_skip_limits_label() -> None:
    tracker = pool_of(pooled(IssueIdentifier("MB-2"), Priority.low, labels=skip_limits()))
    dry = DrainRequest.fake().model_copy(update={"dry_run": DryRun(True)})
    _ = draining(tracker, request=dry)
    assert (
        tracker.read_issue(IssueIdentifier("MB-2")).labels.matching(
            PoolSettings.fake().skip_limits_label
        )
        is not None
    )


def test_a_ticket_another_host_wins_keeps_its_skip_limits_label() -> None:
    tracker = pool_of(pooled(IssueIdentifier("MB-2"), Priority.low, labels=skip_limits()))
    _ = draining(tracker, claims=RacedRegistry(IssueIdentifier("MB-2")))
    assert (
        tracker.read_issue(IssueIdentifier("MB-2")).labels.matching(
            PoolSettings.fake().skip_limits_label
        )
        is not None
    )


def test_an_urgent_ticket_keeps_to_the_limits() -> None:
    tracker = pool_of(
        pooled(IssueIdentifier("MB-2"), Priority.urgent, state=StateName("Grilling")),
        elsewhere=(in_progress(IssueIdentifier("MB-10"), StateName("Grilling")),),
    )
    assert picked(draining(tracker)) == ()


def test_a_skip_limits_label_the_tracker_lacks_refuses_the_pass() -> None:
    tracker = pool_of(
        pooled(IssueIdentifier("MB-1"), Priority.low),
        labels=LabelNames((LabelName("claimed"), *FlowLabels.fake().labels.root)),
    )
    claims = FakeClaimRegistry()
    with pytest.raises(UnknownLabelError, match="skip-limits"):
        _ = draining(tracker, claims=claims)
    assert holders(claims, IssueIdentifier("MB-1")) == ()


def drain_logged(
    caplog: pytest.LogCaptureFixture, tracker: FakeTicketTracker, pool: PoolSettings | None = None
) -> None:
    with caplog.at_level(logging.INFO):
        _ = draining(tracker, pool=pool)


def test_the_outcome_says_why_a_ticket_in_the_view_is_not_ready() -> None:
    tracker = pool_of(
        pooled(IssueIdentifier("MB-2"), Priority.high, labels=LabelNames((LabelName("claimed"),))),
        pooled(IssueIdentifier("MB-3"), Priority.high, state=StateName("QA")),
        pooled(IssueIdentifier("MB-4"), Priority.high, state=None),
    )
    claimed = UnreadyReason("it is already claimed")
    unworked = UnreadyReason("no agent works tickets in QA")
    stateless = UnreadyReason("it has no flow state")
    outcome = draining(tracker)
    assert tuple(
        (unready.ticket.issue.identifier, unready.reason) for unready in outcome.unready
    ) == (
        (IssueIdentifier("MB-2"), claimed),
        (IssueIdentifier("MB-3"), unworked),
        (IssueIdentifier("MB-4"), stateless),
    )


def test_a_ticket_with_two_flow_labels_is_not_ready_and_the_outcome_says_why() -> None:
    tracker = pool_of(
        pooled(IssueIdentifier("MB-1"), Priority.low),
        pooled(IssueIdentifier("MB-2"), Priority.high, labels=LabelNames((LabelName("QA"),))),
    )
    conflicting = UnreadyReason(
        "The ticket carries the flow labels Specced, QA, but may carry only one."
    )
    outcome = draining(tracker)
    assert picked(outcome) == (IssueIdentifier("MB-1"),)
    assert tuple(
        (unready.ticket.issue.identifier, unready.reason) for unready in outcome.unready
    ) == ((IssueIdentifier("MB-2"), conflicting),)


def test_the_outcome_names_the_tickets_left_when_the_pool_fills() -> None:
    total = Limit(1)
    outcome = draining(standard_pool(), pool=pool_with_total(total))
    assert outcome.full is not None
    assert outcome.full.total == total
    assert outcome.full.left.identifiers() == (IssueIdentifier("MB-1"),)


def test_the_outcome_of_a_pass_with_room_left_is_not_full() -> None:
    assert draining(standard_pool()).full is None


def test_the_log_names_each_ticket_started(caplog: pytest.LogCaptureFixture) -> None:
    drain_logged(caplog, standard_pool())
    log = caplog.text
    assert "Taking MB-2 (high, Specced)…" in log
    assert "Taking MB-1 (low, Specced)…" in log


def test_a_dry_run_logs_each_ticket_it_would_start(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        _ = draining(
            standard_pool(),
            request=DrainRequest.fake().model_copy(update={"dry_run": DryRun(True)}),
        )
    assert "Would start MB-2 (high, Specced)." in caplog.text


@pytest.mark.parametrize(
    "activity",
    [
        "Draining the pool",
        f"Listing the tickets in view {PoolSettings.fake().view.root}",
        "Listing the tickets labelled claimed",
        "Taking MB-2 (high, Specced)",
        "Reading MB-2",
        f"Claiming MB-2 for worktree MB-2 on {DrainRequest.fake().host.root}",
        "Labelling MB-2 as claimed",
        f"Assigning MB-2 to {WorkspaceSettings.fake().assignee.root}",
        "Creating worktree MB-2",
    ],
)
def test_the_log_brackets_each_activity_of_a_pass_with_its_start_and_finish(
    caplog: pytest.LogCaptureFixture, activity: str
) -> None:
    drain_logged(caplog, standard_pool())
    log = caplog.text
    started = log.index(f"{activity}…")
    assert re.search(rf"{re.escape(activity)} took \d+\.\ds\.", log[started:])


def test_the_log_says_a_ticket_labelled_skip_limits_overrode_the_limits(
    caplog: pytest.LogCaptureFixture,
) -> None:
    tracker = pool_of(
        pooled(
            IssueIdentifier("MB-2"), Priority.low, state=StateName("Grilling"), labels=skip_limits()
        ),
        elsewhere=(in_progress(IssueIdentifier("MB-10"), StateName("Grilling")),),
    )
    drain_logged(caplog, tracker)
    assert (
        "MB-2 is labelled skip-limits, so it starts although Grilling is at its limit of 1."
        in caplog.text
    )


def test_a_ticket_whose_label_is_full_is_skipped_for_the_next() -> None:
    tracker = pool_of(
        pooled(IssueIdentifier("MB-1"), Priority.low),
        pooled(IssueIdentifier("MB-2"), Priority.high, labels=refactors()),
        labels=labels_with_refactor(),
        elsewhere=(in_progress(IssueIdentifier("MB-10"), StateName("Review"), labels=refactors()),),
    )
    assert picked(draining(tracker, pool=pool_capping_refactors_at(Limit(1)))) == (
        IssueIdentifier("MB-1"),
    )


def test_a_ticket_started_in_the_pass_fills_its_label() -> None:
    tracker = pool_of(
        pooled(IssueIdentifier("MB-1"), Priority.low, labels=refactors()),
        pooled(IssueIdentifier("MB-2"), Priority.high, labels=refactors()),
        pooled(IssueIdentifier("MB-3"), Priority.no_priority),
        labels=labels_with_refactor(),
    )
    assert picked(draining(tracker, pool=pool_capping_refactors_at(Limit(1)))) == (
        IssueIdentifier("MB-2"),
        IssueIdentifier("MB-3"),
    )


def test_the_outcome_names_each_skipped_ticket_and_why() -> None:
    tracker = pool_of(
        pooled(IssueIdentifier("MB-1"), Priority.low, labels=refactors()),
        pooled(IssueIdentifier("MB-2"), Priority.high, labels=refactors()),
        labels=labels_with_refactor(),
    )
    outcome = draining(tracker, pool=pool_capping_refactors_at(Limit(1)))
    assert tuple((skip.ticket.issue.identifier, skip.refusal) for skip in outcome.skipped) == (
        (IssueIdentifier("MB-1"), Refusal("label refactor is at its limit of 1")),
    )


def test_a_limited_label_the_tracker_lacks_refuses_the_pass() -> None:
    tracker = pool_of(pooled(IssueIdentifier("MB-1"), Priority.low))
    claims = FakeClaimRegistry()
    with pytest.raises(UnknownLabelError, match="refactor"):
        _ = draining(tracker, claims=claims, pool=pool_capping_refactors_at(Limit(1)))
    assert holders(claims, IssueIdentifier("MB-1")) == ()


def test_a_ticket_labelled_skip_limits_starts_past_its_label_limit() -> None:
    tracker = pool_of(
        pooled(
            IssueIdentifier("MB-2"),
            Priority.low,
            labels=LabelNames((*refactors().root, *skip_limits().root)),
        ),
        labels=labels_with_refactor(),
        elsewhere=(in_progress(IssueIdentifier("MB-10"), StateName("Review"), labels=refactors()),),
    )
    outcome = draining(tracker, pool=pool_capping_refactors_at(Limit(1)))
    assert picked(outcome) == (IssueIdentifier("MB-2"),)
    assert outcome.skipped == ()


def outcome_of(
    ready: tuple[IssueIdentifier, ...], picked: tuple[IssueIdentifier, ...] = ()
) -> DrainOutcome:
    def tickets(identifiers: tuple[IssueIdentifier, ...]) -> PoolTickets:
        return PoolTickets(
            tuple(
                PoolTicket.fake().model_copy(
                    update={
                        "issue": PoolTicket.fake().issue.model_copy(
                            update={"identifier": identifier}
                        )
                    }
                )
                for identifier in identifiers
            )
        )

    return DrainOutcome(ready=tickets(ready), picked=tickets(picked), skipped=())


def test_a_first_pass_counts_as_changed() -> None:
    assert outcome_of((IssueIdentifier("MB-1"),)).changed_since(None) == Changed(True)


def test_a_pass_matching_the_last_counts_as_unchanged() -> None:
    previous = outcome_of((IssueIdentifier("MB-1"), IssueIdentifier("MB-2")))
    current = outcome_of((IssueIdentifier("MB-2"), IssueIdentifier("MB-1")))
    assert current.changed_since(previous) == Changed(False)


def test_a_pass_with_a_different_ready_set_counts_as_changed() -> None:
    previous = outcome_of((IssueIdentifier("MB-1"),))
    current = outcome_of((IssueIdentifier("MB-1"), IssueIdentifier("MB-2")))
    assert current.changed_since(previous) == Changed(True)


def test_a_pass_that_started_a_ticket_counts_as_changed() -> None:
    started = outcome_of((IssueIdentifier("MB-1"),), picked=(IssueIdentifier("MB-1"),))
    assert started.changed_since(started) == Changed(True)
