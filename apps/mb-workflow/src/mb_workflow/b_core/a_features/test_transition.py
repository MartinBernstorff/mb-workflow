import pytest

from mb_workflow.b_core.a_features.transition import LinkedTicketTransition
from mb_workflow.b_core.b_domain_services.flow_transition import Force
from mb_workflow.b_core.c_secondary_ports.status import FakeStatusStore
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import FakeTicketTracker, TrackedIssue
from mb_workflow.b_core.c_secondary_ports.workspace_manager import FakeWorkspaceManager
from mb_workflow.b_core.d_domain_model.flow import EventName, StateName
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier, LabelName, LabelNames
from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses
from mb_workflow.b_core.d_domain_model.workspace import (
    UnlinkedWorktreeError,
    Worktree,
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
    _ = LinkedTicketTransition.transition_linked_ticket(
        store=FakeStatusStore(StateName("Implementing")),
        tracker=tracker,
        manager=manager,
        wanted=FlowLabels.fake(),
        statuses=TicketStatuses.fake(),
        event=EventName("qa"),
        force=Force(False),
    ).unwrap()
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().labels == LabelNames(
        (LabelName.fake(), LabelName("QA"))
    )


def test_a_worktree_with_no_linked_issue_leaves_the_board_where_it_was() -> None:
    store = FakeStatusStore(StateName("Implementing"))
    unlinked = Worktree.fake().model_copy(update={"issue": None})
    manager = FakeWorkspaceManager(Worktrees((unlinked,)), unlinked.path)
    with pytest.raises(UnlinkedWorktreeError, match="no linked Linear issue"):
        _ = LinkedTicketTransition.transition_linked_ticket(
            store=store,
            tracker=seeded_tracker(),
            manager=manager,
            wanted=FlowLabels.fake(),
            statuses=TicketStatuses.fake(),
            event=EventName("qa"),
            force=Force(False),
        ).unwrap()
    assert store.read() == StateName("Implementing")
