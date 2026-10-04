import pytest
from safe_result import Err

from mb_workflow.b_core.a_features.transition import LinkedTicketTransition
from mb_workflow.b_core.b_domain_services.flow_transition import Force
from mb_workflow.b_core.c_secondary_ports.status import FakeStatusStore
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import FakeTicketTracker, TrackedIssue
from mb_workflow.b_core.c_secondary_ports.workspace_manager import (
    FakeWorkspaceManager,
    WorkspaceManagerError,
)
from mb_workflow.b_core.d_domain_model.flow import EventName, StateName
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier, LabelName, LabelNames
from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses
from mb_workflow.b_core.d_domain_model.workspace import (
    UnlinkedWorktreeError,
    Worktree,
    WorktreeName,
    WorktreePath,
    Worktrees,
)


def seeded_tracker() -> FakeTicketTracker:
    wanted = FlowLabels.fake()
    return FakeTicketTracker(
        LabelNames((*wanted.labels.root, LabelName.fake())),
        (TrackedIssue.fake(),),
        groups={wanted.group: wanted.labels},
    )


def test_labels_the_issue_linked_to_the_worktree_you_stand_in() -> None:
    tracker = seeded_tracker()
    manager = FakeWorkspaceManager(Worktrees.fake(), WorktreePath.fake())
    _ = LinkedTicketTransition.move_linked_ticket(
        board_at=lambda _: FakeStatusStore(StateName("implementing")),
        tracker=tracker,
        manager=manager,
        wanted=FlowLabels.fake(),
        statuses=TicketStatuses.fake(),
        event=EventName("qa"),
        force=Force(False),
        ticket=None,
    ).unwrap()
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().labels == LabelNames(
        (LabelName.fake(), LabelName("qa"))
    )


def test_a_worktree_with_no_linked_issue_leaves_the_board_where_it_was() -> None:
    store = FakeStatusStore(StateName("implementing"))
    unlinked = Worktree.fake().model_copy(update={"issue": None})
    manager = FakeWorkspaceManager(Worktrees((unlinked,)), unlinked.path)
    with pytest.raises(UnlinkedWorktreeError, match="no linked Linear issue"):
        _ = LinkedTicketTransition.move_linked_ticket(
            board_at=lambda _: store,
            tracker=seeded_tracker(),
            manager=manager,
            wanted=FlowLabels.fake(),
            statuses=TicketStatuses.fake(),
            event=EventName("qa"),
            force=Force(False),
            ticket=None,
        ).unwrap()
    assert store.read().unwrap() == StateName("implementing")


def test_an_unlisted_current_worktree_leaves_the_ticket_where_it_was() -> None:
    tracker = seeded_tracker()
    before = tracker.read_issue(IssueIdentifier.fake()).unwrap()
    refused = LinkedTicketTransition.move_linked_ticket(
        board_at=lambda _: FakeStatusStore(StateName("implementing")),
        tracker=tracker,
        manager=FakeWorkspaceManager(Worktrees(()), WorktreePath.fake()),
        wanted=FlowLabels.fake(),
        statuses=TicketStatuses.fake(),
        event=EventName("qa"),
        force=Force(False),
        ticket=None,
    )
    assert refused == Err(WorkspaceManagerError(f"No worktree is at {WorktreePath.fake().root}."))
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap() == before


def test_a_named_ticket_moves_the_board_of_the_worktree_linked_to_it() -> None:
    implementing = StateName("implementing")
    qa = StateName("qa")
    tracker = seeded_tracker()
    here = Worktree.fake().model_copy(update={"issue": None})
    linked = Worktree.fake().model_copy(
        update={"path": WorktreePath.fake().sibling(WorktreeName("linked"))}
    )
    boards = {here.path: FakeStatusStore(implementing), linked.path: FakeStatusStore(implementing)}
    moved = LinkedTicketTransition.move_linked_ticket(
        board_at=lambda worktree: boards[worktree.path],
        tracker=tracker,
        manager=FakeWorkspaceManager(Worktrees((here, linked)), here.path),
        wanted=FlowLabels.fake(),
        statuses=TicketStatuses.fake(),
        event=EventName(qa.root),
        force=Force(False),
        ticket=IssueIdentifier.fake(),
    )
    assert moved.unwrap() == qa
    assert boards[linked.path].read().unwrap() == qa
    assert boards[here.path].read().unwrap() == implementing
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().labels == LabelNames(
        (LabelName.fake(), LabelName(qa.root))
    )


def test_a_named_ticket_no_worktree_links_to_leaves_the_ticket_where_it_was() -> None:
    tracker = seeded_tracker()
    before = tracker.read_issue(IssueIdentifier.fake()).unwrap()
    refused = LinkedTicketTransition.move_linked_ticket(
        board_at=lambda _: FakeStatusStore(StateName("implementing")),
        tracker=tracker,
        manager=FakeWorkspaceManager(
            Worktrees((Worktree.fake().model_copy(update={"issue": None}),)), WorktreePath.fake()
        ),
        wanted=FlowLabels.fake(),
        statuses=TicketStatuses.fake(),
        event=EventName("qa"),
        force=Force(False),
        ticket=IssueIdentifier.fake(),
    )
    assert refused == Err(
        WorkspaceManagerError(f"No worktree is linked to {IssueIdentifier.fake().root}.")
    )
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap() == before
