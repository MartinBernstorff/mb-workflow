import pytest
from assertions import Assert
from safe_result import Err, Result

from mb_workflow.b_core.a_features.transition import WorktreeTransition
from mb_workflow.b_core.b_domain_services.flow_transition import Force
from mb_workflow.b_core.c_secondary_ports.status import FakeStatusStore
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import FakeTicketTracker, TrackedIssue
from mb_workflow.b_core.c_secondary_ports.workspace_manager import (
    FakeWorkspaceManager,
    WorkspaceManagerError,
)
from mb_workflow.b_core.d_domain_model.flow import EventName, FlowError, StateName
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
from mb_workflow.b_core.d_domain_model.issue import (
    IssueIdentifier,
    IssueStatusName,
    LabelName,
    LabelNames,
)
from mb_workflow.b_core.d_domain_model.pull_request import PrNumber
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
    _ = WorktreeTransition.move_worktree(
        board_at=lambda _: FakeStatusStore(StateName("agent-reviewing")),
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
    store = FakeStatusStore(StateName("agent-reviewing"))
    unlinked = Worktree.fake().model_copy(update={"issue": None, "pull_request": None})
    manager = FakeWorkspaceManager(Worktrees((unlinked,)), unlinked.path)
    with pytest.raises(UnlinkedWorktreeError, match="no linked Linear issue"):
        _ = WorktreeTransition.move_worktree(
            board_at=lambda _: store,
            tracker=seeded_tracker(),
            manager=manager,
            wanted=FlowLabels.fake(),
            statuses=TicketStatuses.fake(),
            event=EventName("qa"),
            force=Force(False),
            ticket=None,
        ).unwrap()
    assert store.read().unwrap() == StateName("agent-reviewing")


def test_an_unlisted_current_worktree_leaves_the_ticket_where_it_was() -> None:
    tracker = seeded_tracker()
    before = tracker.read_issue(IssueIdentifier.fake()).unwrap()
    refused = WorktreeTransition.move_worktree(
        board_at=lambda _: FakeStatusStore(StateName("agent-reviewing")),
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
    agent_reviewing = StateName("agent-reviewing")
    qa = StateName("qa")
    tracker = seeded_tracker()
    here = Worktree.fake().model_copy(update={"issue": None})
    linked = Worktree.fake().model_copy(
        update={"path": WorktreePath.fake().sibling(WorktreeName("linked"))}
    )
    boards = {
        here.path: FakeStatusStore(agent_reviewing),
        linked.path: FakeStatusStore(agent_reviewing),
    }
    moved = WorktreeTransition.move_worktree(
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
    assert boards[here.path].read().unwrap() == agent_reviewing
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().labels == LabelNames(
        (LabelName.fake(), LabelName(qa.root))
    )


def test_a_named_ticket_no_worktree_links_to_leaves_the_ticket_where_it_was() -> None:
    tracker = seeded_tracker()
    before = tracker.read_issue(IssueIdentifier.fake()).unwrap()
    refused = WorktreeTransition.move_worktree(
        board_at=lambda _: FakeStatusStore(StateName("agent-reviewing")),
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


def test_the_agent_review_moves_the_ticket_and_the_board_to_agent_reviewing() -> None:
    agent_reviewing = StateName("agent-reviewing")
    # A status no neighbouring state maps to, so only agent-reviewing's own mapping can set it.
    reviewing_status = IssueStatusName("Done")
    statuses = TicketStatuses({**TicketStatuses.fake().root, agent_reviewing: reviewing_status})
    tracker = seeded_tracker()
    board = FakeStatusStore(StateName("implementing"))
    moved = WorktreeTransition.move_worktree(
        board_at=lambda _: board,
        tracker=tracker,
        manager=FakeWorkspaceManager(Worktrees.fake(), WorktreePath.fake()),
        wanted=FlowLabels.fake(),
        statuses=statuses,
        event=EventName("agent-review"),
        force=Force(False),
        ticket=None,
    )
    assert moved.unwrap() == agent_reviewing
    assert board.read().unwrap() == agent_reviewing
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().status == reviewing_status


def review_worktree() -> Worktree:
    return Worktree.fake().model_copy(update={"issue": None})


def moved_review(
    worktree: Worktree, board: FakeStatusStore, tracker: FakeTicketTracker, event: EventName
) -> Result[StateName, Exception]:
    return WorktreeTransition.move_worktree(
        board_at=lambda _: board,
        tracker=tracker,
        manager=FakeWorkspaceManager(Worktrees((worktree,)), worktree.path),
        wanted=FlowLabels.fake(),
        statuses=TicketStatuses.fake(),
        event=event,
        force=Force(False),
        ticket=None,
    )


def test_reviewed_hands_a_teammate_s_pull_request_from_the_agent_to_me() -> None:
    reviewing = StateName("reviewing")
    tracker = seeded_tracker()
    before = tracker.read_issue(IssueIdentifier.fake()).unwrap()
    board = FakeStatusStore(StateName("agent-reviewing"))
    moved = moved_review(review_worktree(), board, tracker, EventName("reviewed"))
    assert moved.unwrap() == reviewing
    assert board.read().unwrap() == reviewing
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap() == before


def test_reviewed_is_refused_on_a_worktree_for_my_own_ticket() -> None:
    agent_reviewing = StateName("agent-reviewing")
    tracker = seeded_tracker()
    before = tracker.read_issue(IssueIdentifier.fake()).unwrap()
    board = FakeStatusStore(agent_reviewing)
    refused = moved_review(Worktree.fake(), board, tracker, EventName("reviewed"))
    error = Assert.that(refused.error).is_instance(FlowError)
    Assert.that(str(error)).contains(f"your own ticket {IssueIdentifier.fake().root}")
    assert board.read().unwrap() == agent_reviewing
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap() == before


def test_reviewed_is_refused_on_a_worktree_linked_to_nothing() -> None:
    agent_reviewing = StateName("agent-reviewing")
    bare = Worktree.fake().model_copy(update={"issue": None, "pull_request": None})
    board = FakeStatusStore(agent_reviewing)
    refused = moved_review(bare, board, seeded_tracker(), EventName("reviewed"))
    error = Assert.that(refused.error).is_instance(FlowError)
    Assert.that(str(error)).contains("is linked to no pull request")
    assert board.read().unwrap() == agent_reviewing


@pytest.mark.parametrize("event", ["qa", "implement", "agent-review", "merged"])
def test_my_own_ticket_s_events_are_refused_on_a_review_worktree(event: str) -> None:
    agent_reviewing = StateName("agent-reviewing")
    tracker = seeded_tracker()
    before = tracker.read_issue(IssueIdentifier.fake()).unwrap()
    board = FakeStatusStore(agent_reviewing)
    refused = moved_review(review_worktree(), board, tracker, EventName(event))
    error = Assert.that(refused.error).is_instance(FlowError)
    Assert.that(str(error)).contains(f"reviews PR #{PrNumber.fake().root}")
    Assert.that(str(error)).contains("which has no ticket of yours")
    assert board.read().unwrap() == agent_reviewing
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap() == before


def test_forcing_my_own_ticket_s_event_on_a_review_worktree_is_still_refused() -> None:
    agent_reviewing = StateName("agent-reviewing")
    worktree = review_worktree()
    board = FakeStatusStore(agent_reviewing)
    refused = WorktreeTransition.move_worktree(
        board_at=lambda _: board,
        tracker=seeded_tracker(),
        manager=FakeWorkspaceManager(Worktrees((worktree,)), worktree.path),
        wanted=FlowLabels.fake(),
        statuses=TicketStatuses.fake(),
        event=EventName("qa"),
        force=Force(True),
        ticket=None,
    )
    _ = Assert.that(refused.error).is_instance(FlowError)
    assert board.read().unwrap() == agent_reviewing


def test_a_review_already_handed_to_me_cannot_be_handed_over_again() -> None:
    reviewing = StateName("reviewing")
    board = FakeStatusStore(reviewing)
    refused = moved_review(review_worktree(), board, seeded_tracker(), EventName("reviewed"))
    error = Assert.that(refused.error).is_instance(FlowError)
    Assert.that(str(error)).contains("reviewed is not legal from reviewing")
    assert board.read().unwrap() == reviewing
