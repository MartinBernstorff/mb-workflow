from typing import TYPE_CHECKING

import pytest
from safe_result import Err

from mb_workflow.b_core.b_domain_services.flow_label_check import MissingFlowLabelsError
from mb_workflow.b_core.b_domain_services.flow_transition import Force, transition
from mb_workflow.b_core.c_secondary_ports.status import FakeStatusStore
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
    FakeTicketTracker,
    TicketTrackerError,
    TrackedIssue,
)
from mb_workflow.b_core.d_domain_model.flow import EventName, FlowError, StateName, WorkflowChart
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
    TeamKey,
)
from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses

if TYPE_CHECKING:
    from safe_result import Result


def mapped_statuses() -> IssueStatuses:
    names = dict.fromkeys(TicketStatuses.fake().root.values())
    return IssueStatuses(tuple(IssueStatus(name=name, type=StatusType.started) for name in names))


def seeded_tracker(held: LabelNames) -> FakeTicketTracker:
    wanted = FlowLabels.fake()
    issue = Issue.fake().model_copy(update={"labels": held})
    return FakeTicketTracker(
        LabelNames((*wanted.labels.root, LabelName.fake())),
        (TrackedIssue.fake().model_copy(update={"issue": issue}),),
        statuses=mapped_statuses(),
        groups={wanted.group: wanted.labels},
    )


def transition_with_fake_flow_labels(
    store: FakeStatusStore, tracker: FakeTicketTracker, event: EventName, force: Force
) -> Result[StateName, TicketTrackerError | MissingFlowLabelsError]:
    return transition(
        chart=WorkflowChart,
        store=store,
        tracker=tracker,
        issue=IssueIdentifier.fake(),
        wanted=FlowLabels.fake(),
        statuses=TicketStatuses.fake(),
        event=event,
        force=force,
    )


def test_a_legal_event_writes_the_target_state_to_the_store() -> None:
    store = FakeStatusStore(StateName("Implementing"))
    tracker = seeded_tracker(LabelNames(()))
    target = transition_with_fake_flow_labels(
        store, tracker, EventName("qa"), Force(False)
    ).unwrap()
    assert target == StateName("QA")
    assert store.read() == StateName("QA")


def test_a_legal_event_writes_the_relabelled_labels_to_the_ticket() -> None:
    tracker = seeded_tracker(LabelNames((LabelName("Implementing"), LabelName.fake())))
    store = FakeStatusStore(StateName("Implementing"))
    _ = transition_with_fake_flow_labels(store, tracker, EventName("qa"), Force(False)).unwrap()
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().labels == LabelNames(
        (LabelName.fake(), LabelName("QA"))
    )


def test_a_legal_event_sets_the_ticket_to_the_status_the_target_state_maps_to() -> None:
    store = FakeStatusStore(StateName("QA"))
    tracker = seeded_tracker(LabelNames(()))
    _ = transition_with_fake_flow_labels(store, tracker, EventName("ready"), Force(False)).unwrap()
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().status == IssueStatusName(
        "In Review"
    )


def test_an_illegal_event_leaves_the_store_and_the_ticket_where_they_were() -> None:
    store = FakeStatusStore(StateName("Grilling"))
    tracker = seeded_tracker(LabelNames((LabelName("Grilling"),)))
    with pytest.raises(FlowError, match="merge is not legal from Grilling"):
        _ = transition_with_fake_flow_labels(
            store, tracker, EventName("merge"), Force(False)
        ).unwrap()
    assert store.read() == StateName("Grilling")
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().labels == LabelNames(
        (LabelName("Grilling"),)
    )
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().status == IssueStatusName.fake()


def test_forcing_writes_the_target_state_without_validating() -> None:
    store = FakeStatusStore(StateName("Grilling"))
    tracker = seeded_tracker(LabelNames(()))
    target = transition_with_fake_flow_labels(
        store, tracker, EventName("merged"), Force(True)
    ).unwrap()
    assert target == StateName("Merged")
    assert store.read() == StateName("Merged")
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().labels == LabelNames(
        (LabelName("Merged"),)
    )
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().status == IssueStatusName("Done")


def test_a_refused_ticket_write_leaves_the_board_where_it_was() -> None:
    wanted = FlowLabels.fake()
    store = FakeStatusStore(StateName("Implementing"))
    # The ticket holds a label the tracker does not know, so the write refuses.
    tracker = FakeTicketTracker(
        wanted.labels,
        (TrackedIssue.fake(),),
        statuses=mapped_statuses(),
        groups={wanted.group: wanted.labels},
    )
    with pytest.raises(TicketTrackerError, match=f"No label is named {LabelName.fake().root}"):
        _ = transition_with_fake_flow_labels(store, tracker, EventName("qa"), Force(False)).unwrap()
    assert store.read() == StateName("Implementing")
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().status == IssueStatusName.fake()


def test_a_status_the_tracker_lacks_leaves_the_ticket_and_the_board_where_they_were() -> None:
    wanted = FlowLabels.fake()
    store = FakeStatusStore(StateName("QA"))
    tracker = FakeTicketTracker(
        LabelNames((*wanted.labels.root, LabelName.fake())),
        (TrackedIssue.fake(),),
        statuses=IssueStatuses((IssueStatus.fake(),)),
        groups={wanted.group: wanted.labels},
    )
    with pytest.raises(TicketTrackerError, match="No status is named In Review"):
        _ = transition_with_fake_flow_labels(
            store, tracker, EventName("ready"), Force(False)
        ).unwrap()
    assert store.read() == StateName("QA")
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().labels == Issue.fake().labels


def test_missing_flow_labels_point_to_seed_labels_and_leave_the_board_alone() -> None:
    store = FakeStatusStore(StateName("Implementing"))
    tracker = FakeTicketTracker(LabelNames.fake(), (TrackedIssue.fake(),))
    refused = transition_with_fake_flow_labels(store, tracker, EventName("qa"), Force(False))
    assert isinstance(refused, Err)
    assert isinstance(refused.error, MissingFlowLabelsError)
    assert "mw flow seed-labels" in str(refused.error)
    assert store.read() == StateName("Implementing")


# The ticket carries no labels, so only the flow label a transition writes is left on it.
class TeamTrackers:
    @staticmethod
    def with_issue_in_team(
        issue_team: TeamKey, team_groups: dict[TeamKey, LabelNames], workspace: LabelNames
    ) -> FakeTicketTracker:
        wanted = FlowLabels.fake()
        issue = Issue.fake().model_copy(update={"labels": LabelNames(())})
        return FakeTicketTracker(
            workspace,
            (TrackedIssue.fake().model_copy(update={"issue": issue, "team": issue_team}),),
            statuses=mapped_statuses(),
            groups={wanted.group: workspace} if workspace.root else None,
            team_groups={(team, wanted.group): labels for team, labels in team_groups.items()},
        )


def test_a_transition_writes_the_flow_label_of_the_tickets_own_team() -> None:
    ops = TeamKey("OPS")
    labels = FlowLabels.fake().labels
    tracker = TeamTrackers.with_issue_in_team(
        ops, {TeamKey.fake(): labels, ops: labels}, LabelNames(())
    )
    store = FakeStatusStore(StateName("Implementing"))
    _ = transition_with_fake_flow_labels(store, tracker, EventName("qa"), Force(False)).unwrap()
    qa = LabelName("QA")
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().labels == LabelNames((qa,))


def test_a_transition_falls_back_to_workspace_flow_labels() -> None:
    tracker = TeamTrackers.with_issue_in_team(TeamKey("OPS"), {}, FlowLabels.fake().labels)
    store = FakeStatusStore(StateName("Implementing"))
    _ = transition_with_fake_flow_labels(store, tracker, EventName("qa"), Force(False)).unwrap()
    qa = LabelName("QA")
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().labels == LabelNames((qa,))


def test_another_teams_flow_labels_leave_the_ticket_and_the_board_alone() -> None:
    tracker = TeamTrackers.with_issue_in_team(
        TeamKey("OPS"), {TeamKey.fake(): FlowLabels.fake().labels}, LabelNames(())
    )
    store = FakeStatusStore(StateName("Implementing"))
    refused = transition_with_fake_flow_labels(store, tracker, EventName("qa"), Force(False))
    assert isinstance(refused, Err)
    assert isinstance(refused.error, MissingFlowLabelsError)
    assert store.read() == StateName("Implementing")
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().labels == LabelNames(())
