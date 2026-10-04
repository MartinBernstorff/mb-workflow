import re

import pytest
from safe_result import Err, Ok, Result

from mb_workflow.b_core.b_domain_services.flow_label_check import MissingFlowLabelsError
from mb_workflow.b_core.b_domain_services.flow_transition import (
    FlowStateStep,
    FlowTransition,
    Force,
)
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
) -> Result[StateName, FlowError | TicketTrackerError | MissingFlowLabelsError]:
    return FlowTransition.move_ticket(
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
    store = FakeStatusStore(StateName("implementing"))
    tracker = seeded_tracker(LabelNames(()))
    target = transition_with_fake_flow_labels(store, tracker, EventName("qa"), Force(False))
    assert target == Ok(StateName("qa"))
    assert store.read() == StateName("qa")


def test_a_legal_event_writes_the_relabelled_labels_to_the_ticket() -> None:
    tracker = seeded_tracker(LabelNames((LabelName("implementing"), LabelName.fake())))
    store = FakeStatusStore(StateName("implementing"))
    _ = transition_with_fake_flow_labels(store, tracker, EventName("qa"), Force(False)).unwrap()
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().labels == LabelNames(
        (LabelName.fake(), LabelName("qa"))
    )


def test_a_legal_event_sets_the_ticket_to_the_status_the_target_state_maps_to() -> None:
    store = FakeStatusStore(StateName("qa"))
    tracker = seeded_tracker(LabelNames(()))
    _ = transition_with_fake_flow_labels(store, tracker, EventName("ready"), Force(False)).unwrap()
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().status == IssueStatusName(
        "In Review"
    )


def test_an_illegal_event_leaves_the_store_and_the_ticket_where_they_were() -> None:
    store = FakeStatusStore(StateName("grill"))
    tracker = seeded_tracker(LabelNames((LabelName("grill"),)))
    refused = transition_with_fake_flow_labels(store, tracker, EventName("merge"), Force(False))
    assert isinstance(refused, Err)
    assert isinstance(refused.error, FlowError)
    assert re.search("merge is not legal from grill", str(refused.error))
    assert store.read() == StateName("grill")
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().labels == LabelNames(
        (LabelName("grill"),)
    )
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().status == IssueStatusName.fake()


def test_forcing_writes_the_target_state_without_validating() -> None:
    store = FakeStatusStore(StateName("grill"))
    tracker = seeded_tracker(LabelNames(()))
    target = transition_with_fake_flow_labels(store, tracker, EventName("merged"), Force(True))
    assert target == Ok(StateName("merged"))
    assert store.read() == StateName("merged")
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().labels == LabelNames(
        (LabelName("merged"),)
    )
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().status == IssueStatusName("Done")


def test_a_refused_ticket_write_leaves_the_board_where_it_was() -> None:
    wanted = FlowLabels.fake()
    store = FakeStatusStore(StateName("implementing"))
    # The ticket holds a label the tracker does not know, so the write refuses.
    tracker = FakeTicketTracker(
        wanted.labels,
        (TrackedIssue.fake(),),
        statuses=mapped_statuses(),
        groups={wanted.group: wanted.labels},
    )
    with pytest.raises(TicketTrackerError, match=f"No label is named {LabelName.fake().root}"):
        _ = transition_with_fake_flow_labels(store, tracker, EventName("qa"), Force(False)).unwrap()
    assert store.read() == StateName("implementing")
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().status == IssueStatusName.fake()


def test_a_status_the_tracker_lacks_leaves_the_ticket_and_the_board_where_they_were() -> None:
    wanted = FlowLabels.fake()
    store = FakeStatusStore(StateName("qa"))
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
    assert store.read() == StateName("qa")
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().labels == Issue.fake().labels


def test_missing_flow_labels_point_to_seed_labels_and_leave_the_board_alone() -> None:
    store = FakeStatusStore(StateName("implementing"))
    tracker = FakeTicketTracker(LabelNames.fake(), (TrackedIssue.fake(),))
    refused = transition_with_fake_flow_labels(store, tracker, EventName("qa"), Force(False))
    assert isinstance(refused, Err)
    assert isinstance(refused.error, MissingFlowLabelsError)
    assert "mw flow seed-labels" in str(refused.error)
    assert store.read() == StateName("implementing")


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
    store = FakeStatusStore(StateName("implementing"))
    _ = transition_with_fake_flow_labels(store, tracker, EventName("qa"), Force(False)).unwrap()
    qa = LabelName("qa")
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().labels == LabelNames((qa,))


def test_a_transition_falls_back_to_workspace_flow_labels() -> None:
    tracker = TeamTrackers.with_issue_in_team(TeamKey("OPS"), {}, FlowLabels.fake().labels)
    store = FakeStatusStore(StateName("implementing"))
    _ = transition_with_fake_flow_labels(store, tracker, EventName("qa"), Force(False)).unwrap()
    qa = LabelName("qa")
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().labels == LabelNames((qa,))


def test_another_teams_flow_labels_leave_the_ticket_and_the_board_alone() -> None:
    tracker = TeamTrackers.with_issue_in_team(
        TeamKey("OPS"), {TeamKey.fake(): FlowLabels.fake().labels}, LabelNames(())
    )
    store = FakeStatusStore(StateName("implementing"))
    refused = transition_with_fake_flow_labels(store, tracker, EventName("qa"), Force(False))
    assert isinstance(refused, Err)
    assert isinstance(refused.error, MissingFlowLabelsError)
    assert store.read() == StateName("implementing")
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().labels == LabelNames(())


def entering(
    tracker: FakeTicketTracker,
    state: StateName,
    previous_state: StateName | None,
    previous_status: IssueStatusName,
) -> FlowStateStep:
    return FlowStateStep(
        tracker=tracker,
        issue=IssueIdentifier.fake(),
        wanted=FlowLabels.fake(),
        statuses=TicketStatuses.fake(),
        state=state,
        previous_state=previous_state,
        previous_status=previous_status,
    )


def test_entering_the_flow_labels_the_ticket_and_sets_the_states_status() -> None:
    tracker = seeded_tracker(LabelNames((LabelName.fake(),)))
    todo = StateName("todo")
    todo_status = IssueStatusName("Todo")
    assert TicketStatuses.fake().of(todo) == todo_status
    assert entering(tracker, todo, None, IssueStatusName.fake()).apply() == Ok(None)
    issue = tracker.read_issue(IssueIdentifier.fake()).unwrap()
    assert issue.labels == LabelNames((LabelName.fake(), LabelName(todo.root)))
    assert issue.status == todo_status


def test_reverting_the_flow_entry_restores_the_labels_and_status() -> None:
    held = LabelNames((LabelName.fake(),))
    tracker = seeded_tracker(held)
    maturing = IssueStatusName("Maturing")
    step = entering(tracker, StateName("todo"), None, maturing)
    _ = step.apply().unwrap()
    assert step.revert() == Ok(None)
    issue = tracker.read_issue(IssueIdentifier.fake()).unwrap()
    assert issue.labels == held
    assert issue.status == maturing


def test_reverting_the_flow_entry_keeps_labels_added_since() -> None:
    tracker = seeded_tracker(LabelNames(()))
    step = entering(tracker, StateName("todo"), None, IssueStatusName("Maturing"))
    _ = step.apply().unwrap()
    added = LabelName.fake()
    tracker.add_label(IssueIdentifier.fake(), added)
    _ = step.revert().unwrap()
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().labels == LabelNames((added,))


def test_reverting_the_flow_state_change_writes_back_the_replaced_flow_label() -> None:
    grill = StateName("grill")
    tracker = seeded_tracker(LabelNames((LabelName.fake(), LabelName(grill.root))))
    maturing = IssueStatusName("Maturing")
    step = entering(tracker, StateName("todo"), grill, maturing)
    _ = step.apply().unwrap()
    assert step.revert() == Ok(None)
    issue = tracker.read_issue(IssueIdentifier.fake()).unwrap()
    assert issue.labels == LabelNames((LabelName.fake(), LabelName(grill.root)))
    assert issue.status == maturing
