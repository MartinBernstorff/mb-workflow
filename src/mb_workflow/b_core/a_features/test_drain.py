from typing import override

import pytest

from mb_workflow.b_core.a_features.autolabel import DryRun
from mb_workflow.b_core.a_features.drain import DrainOutcome, DrainRequest, drain_pool
from mb_workflow.b_core.c_secondary_ports.claims import (
    ClaimRefusedError,
    FakeClaimRegistry,
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
from mb_workflow.b_core.d_domain_model.pool import Limit, PoolLimits, PoolTickets, Priority
from mb_workflow.b_core.d_domain_model.workspace import (
    ProjectSelector,
    TerminalText,
    WorkspaceStatuses,
    WorktreeName,
    WorktreePath,
    Worktrees,
)


def pooled(
    identifier: IssueIdentifier,
    priority: Priority,
    status: IssueStatusName = IssueStatusName("Specced"),
    labels: LabelNames = LabelNames(()),
    blocked_by: tuple[IssueIdentifier, ...] = (),
) -> TrackedIssue:
    return TrackedIssue.fake().model_copy(
        update={
            "issue": Issue.fake().model_copy(
                update={
                    "identifier": identifier,
                    "status": status,
                    "labels": labels,
                }
            ),
            "priority": priority,
            "blocked_by": blocked_by,
        }
    )


def in_progress(identifier: IssueIdentifier, status: IssueStatusName) -> TrackedIssue:
    return pooled(
        identifier,
        Priority.medium,
        status=status,
        labels=LabelNames((LabelName("claimed"),)),
    )


def workflow_statuses(*closing: IssueStatus) -> IssueStatuses:
    final = {StateName(state.name) for state in WorkflowChart.final_states}
    return IssueStatuses(
        (
            *(
                IssueStatus(
                    name=IssueStatusName(state.root),
                    type=StatusType.completed if state in final else StatusType.started,
                )
                for state in StateNames.of_chart(WorkflowChart).root
            ),
            *closing,
        )
    )


def pool_of(
    *tickets: TrackedIssue,
    labels: LabelNames | None = None,
    elsewhere: tuple[TrackedIssue, ...] = (),
    statuses: IssueStatuses | None = None,
) -> FakeTicketTracker:
    return FakeTicketTracker(
        LabelNames((LabelName("claimed"),)) if labels is None else labels,
        (*tickets, *elsewhere),
        statuses=workflow_statuses() if statuses is None else statuses,
        views={PoolSettings.fake().view: tuple(ticket.issue.identifier for ticket in tickets)},
    )


def pool_with_total(total: Limit) -> PoolSettings:
    return PoolSettings.fake().model_copy(
        update={"limits": PoolLimits().model_copy(update={"total": total})}
    )


def picked(outcome: DrainOutcome) -> tuple[IssueIdentifier, ...]:
    return outcome.picked.identifiers()


def standard_pool() -> FakeTicketTracker:
    return pool_of(
        pooled(IssueIdentifier("MB-1"), Priority.low),
        pooled(IssueIdentifier("MB-2"), Priority.urgent),
        pooled(IssueIdentifier("MB-3"), Priority.urgent, status=IssueStatusName("QA")),
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
    return drain_pool(
        tracker=tracker,
        claims=claims or FakeClaimRegistry(),
        manager=manager or fake_manager(),
        board=fake_board(),
        lock=lock or FakeRunLock(),
        tie_break=ReversingTieBreak(),
        workspace=WorkspaceSettings.fake(),
        claim_settings=ClaimSettings(label=LabelName("claimed")),
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
        pooled(IssueIdentifier("MB-2"), Priority.urgent),
        elsewhere=(
            in_progress(IssueIdentifier("MB-10"), IssueStatusName("Implementing")),
            in_progress(IssueIdentifier("MB-11"), IssueStatusName("QA")),
            in_progress(IssueIdentifier("MB-12"), IssueStatusName("Review")),
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
        elsewhere=(in_progress(IssueIdentifier("MB-10"), closing.name),),
        statuses=workflow_statuses(closing),
    )
    assert picked(draining(tracker, pool=pool_with_total(Limit(1)))) == (IssueIdentifier("MB-1"),)


def test_unlabelled_tickets_do_not_count() -> None:
    tracker = pool_of(
        pooled(IssueIdentifier("MB-1"), Priority.low),
        elsewhere=(pooled(IssueIdentifier("MB-10"), Priority.low, status=IssueStatusName("QA")),),
    )
    assert picked(draining(tracker, pool=pool_with_total(Limit(1)))) == (IssueIdentifier("MB-1"),)


def test_a_ticket_whose_status_is_full_is_skipped_for_the_next() -> None:
    tracker = pool_of(
        pooled(IssueIdentifier("MB-1"), Priority.low),
        pooled(IssueIdentifier("MB-2"), Priority.urgent, status=IssueStatusName("Grilling")),
        elsewhere=(in_progress(IssueIdentifier("MB-10"), IssueStatusName("Grilling")),),
    )
    assert picked(draining(tracker)) == (IssueIdentifier("MB-1"),)


def test_a_ticket_started_in_the_pass_fills_its_status() -> None:
    tracker = pool_of(
        pooled(IssueIdentifier("MB-1"), Priority.low, status=IssueStatusName("Grilling")),
        pooled(IssueIdentifier("MB-2"), Priority.urgent, status=IssueStatusName("Grilling")),
    )
    assert picked(draining(tracker)) == (IssueIdentifier("MB-2"),)


def test_a_ticket_carrying_the_claim_label_is_passed_over() -> None:
    tracker = pool_of(
        pooled(IssueIdentifier("MB-1"), Priority.low),
        pooled(
            IssueIdentifier("MB-2"), Priority.urgent, labels=LabelNames((LabelName("claimed"),))
        ),
    )
    assert picked(draining(tracker)) == (IssueIdentifier("MB-1"),)


def test_a_ticket_with_an_unresolved_blocker_is_passed_over() -> None:
    tracker = pool_of(
        pooled(IssueIdentifier("MB-1"), Priority.low),
        pooled(IssueIdentifier("MB-2"), Priority.urgent, blocked_by=(IssueIdentifier("MB-3"),)),
        pooled(IssueIdentifier("MB-3"), Priority.urgent, status=IssueStatusName("QA")),
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
    assert tracker.read_issue(IssueIdentifier("MB-2")).labels == LabelNames(())


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
    with pytest.raises(ClaimRefusedError, match="claimed"):
        _ = draining(tracker, claims=claims)
    assert holders(claims, IssueIdentifier("MB-1")) == ()


def test_a_dry_run_lists_the_tickets_the_limits_allow_and_starts_nothing() -> None:
    manager = fake_manager()
    claims = FakeClaimRegistry()
    tracker = pool_of(
        pooled(IssueIdentifier("MB-1"), Priority.low),
        pooled(IssueIdentifier("MB-2"), Priority.urgent, status=IssueStatusName("Grilling")),
        pooled(IssueIdentifier("MB-3"), Priority.urgent, status=IssueStatusName("QA")),
        pooled(IssueIdentifier("MB-4"), Priority.high),
        pooled(IssueIdentifier("MB-5"), Priority.no_priority),
        elsewhere=(
            in_progress(IssueIdentifier("MB-10"), IssueStatusName("Grilling")),
            in_progress(IssueIdentifier("MB-11"), IssueStatusName("QA")),
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
        pool_of(pooled(IssueIdentifier("MB-3"), Priority.urgent, status=IssueStatusName("QA"))),
        manager=manager,
    )
    assert outcome == DrainOutcome(ready=PoolTickets(()), picked=PoolTickets(()))
    assert manager.worktrees() == Worktrees.fake()


def test_a_pass_is_refused_while_another_holds_the_lock() -> None:
    lock = FakeRunLock()
    claims = FakeClaimRegistry()
    with lock.held(), pytest.raises(AlreadyRunningError):
        _ = draining(standard_pool(), claims=claims, lock=lock)
    assert holders(claims, IssueIdentifier("MB-2")) == ()
