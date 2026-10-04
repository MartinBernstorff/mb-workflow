from typing import TYPE_CHECKING

from assertions import Assert
from safe_result import Err, Ok, Result

from mb_workflow.b_core.b_domain_services.flow_label_check import MissingFlowLabelsError
from mb_workflow.b_core.b_domain_services.flow_transition import (
    FlowStateStep,
    FlowTransition,
    Force,
)
from mb_workflow.b_core.c_secondary_ports.status import FakeStatusStore, UnreachableStatusStore
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
    FakeTicketTracker,
    TicketTrackerError,
    TrackedIssue,
)
from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManagerError
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
    from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore


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
    store: WorkspaceStatusStore, tracker: FakeTicketTracker, event: EventName, force: Force
) -> Result[
    StateName, FlowError | TicketTrackerError | MissingFlowLabelsError | WorkspaceManagerError
]:
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
    Assert.that(target).matches(Ok(StateName("qa")))
    Assert.that(store.read().unwrap()).matches(StateName("qa"))


def test_a_legal_event_writes_the_relabelled_labels_to_the_ticket() -> None:
    tracker = seeded_tracker(LabelNames((LabelName("implementing"), LabelName.fake())))
    store = FakeStatusStore(StateName("implementing"))
    _ = transition_with_fake_flow_labels(store, tracker, EventName("qa"), Force(False)).unwrap()
    Assert.that(tracker.read_issue(IssueIdentifier.fake()).unwrap().labels).matches(
        LabelNames((LabelName.fake(), LabelName("qa")))
    )


def test_a_legal_event_sets_the_ticket_to_the_status_the_target_state_maps_to() -> None:
    store = FakeStatusStore(StateName("qa"))
    tracker = seeded_tracker(LabelNames(()))
    _ = transition_with_fake_flow_labels(store, tracker, EventName("ready"), Force(False)).unwrap()
    Assert.that(tracker.read_issue(IssueIdentifier.fake()).unwrap().status).matches(
        IssueStatusName("In Review")
    )


def test_an_illegal_event_leaves_the_store_and_the_ticket_where_they_were() -> None:
    store = FakeStatusStore(StateName("grill"))
    tracker = seeded_tracker(LabelNames((LabelName("grill"),)))
    refused = transition_with_fake_flow_labels(store, tracker, EventName("merge"), Force(False))
    error = Assert.that(refused.error).is_instance(FlowError)
    Assert.that(str(error)).matches_pattern("merge is not legal from grill")
    Assert.that(store.read().unwrap()).matches(StateName("grill"))
    Assert.that(tracker.read_issue(IssueIdentifier.fake()).unwrap().labels).matches(
        LabelNames((LabelName("grill"),))
    )
    Assert.that(tracker.read_issue(IssueIdentifier.fake()).unwrap().status).matches(
        IssueStatusName.fake()
    )


def test_an_unreachable_board_leaves_the_ticket_where_it_was() -> None:
    tracker = seeded_tracker(LabelNames((LabelName("implementing"),)))
    refused = transition_with_fake_flow_labels(
        UnreachableStatusStore(), tracker, EventName("qa"), Force(False)
    )
    Assert.that(refused).matches(Err(WorkspaceManagerError("The workspace board is unreachable.")))
    Assert.that(tracker.read_issue(IssueIdentifier.fake()).unwrap().labels).matches(
        LabelNames((LabelName("implementing"),))
    )


def test_forcing_writes_the_target_state_without_validating() -> None:
    store = FakeStatusStore(StateName("grill"))
    tracker = seeded_tracker(LabelNames(()))
    target = transition_with_fake_flow_labels(store, tracker, EventName("merged"), Force(True))
    Assert.that(target).matches(Ok(StateName("merged")))
    Assert.that(store.read().unwrap()).matches(StateName("merged"))
    Assert.that(tracker.read_issue(IssueIdentifier.fake()).unwrap().labels).matches(
        LabelNames((LabelName("merged"),))
    )
    Assert.that(tracker.read_issue(IssueIdentifier.fake()).unwrap().status).matches(
        IssueStatusName("Done")
    )


def test_a_refused_ticket_write_leaves_the_board_where_it_was() -> None:
    wanted = FlowLabels.fake()
    store = FakeStatusStore(StateName("implementing"))
    tracker = FakeTicketTracker(
        wanted.labels,
        (TrackedIssue.fake(),),
        statuses=mapped_statuses(),
        groups={wanted.group: wanted.labels},
    )
    refused = transition_with_fake_flow_labels(store, tracker, EventName("qa"), Force(False))
    error = Assert.that(refused.error).exists()
    Assert.that(str(error)).contains(LabelName.fake().root)
    Assert.that(store.read().unwrap()).matches(StateName("implementing"))
    Assert.that(tracker.read_issue(IssueIdentifier.fake()).unwrap().status).matches(
        IssueStatusName.fake()
    )


def test_a_status_the_tracker_lacks_leaves_the_ticket_and_the_board_where_they_were() -> None:
    wanted = FlowLabels.fake()
    store = FakeStatusStore(StateName("qa"))
    tracker = FakeTicketTracker(
        LabelNames((*wanted.labels.root, LabelName.fake())),
        (TrackedIssue.fake(),),
        statuses=IssueStatuses((IssueStatus.fake(),)),
        groups={wanted.group: wanted.labels},
    )
    in_review = TicketStatuses.fake().of(StateName("review"))
    refused = transition_with_fake_flow_labels(store, tracker, EventName("ready"), Force(False))
    error = Assert.that(refused.error).exists()
    Assert.that(str(error)).contains(in_review.root)
    Assert.that(store.read().unwrap()).matches(StateName("qa"))
    Assert.that(tracker.read_issue(IssueIdentifier.fake()).unwrap().labels).matches(
        Issue.fake().labels
    )


def test_missing_flow_labels_point_to_seed_labels_and_leave_the_board_alone() -> None:
    store = FakeStatusStore(StateName("implementing"))
    tracker = FakeTicketTracker(LabelNames.fake(), (TrackedIssue.fake(),))
    refused = transition_with_fake_flow_labels(store, tracker, EventName("qa"), Force(False))
    error = Assert.that(refused.error).is_instance(MissingFlowLabelsError)
    Assert.that(str(error)).contains("mw flow seed-labels")
    Assert.that(store.read().unwrap()).matches(StateName("implementing"))


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
    Assert.that(tracker.read_issue(IssueIdentifier.fake()).unwrap().labels).matches(
        LabelNames((qa,))
    )


def test_a_transition_falls_back_to_workspace_flow_labels() -> None:
    tracker = TeamTrackers.with_issue_in_team(TeamKey("OPS"), {}, FlowLabels.fake().labels)
    store = FakeStatusStore(StateName("implementing"))
    _ = transition_with_fake_flow_labels(store, tracker, EventName("qa"), Force(False)).unwrap()
    qa = LabelName("qa")
    Assert.that(tracker.read_issue(IssueIdentifier.fake()).unwrap().labels).matches(
        LabelNames((qa,))
    )


def test_another_teams_flow_labels_leave_the_ticket_and_the_board_alone() -> None:
    tracker = TeamTrackers.with_issue_in_team(
        TeamKey("OPS"), {TeamKey.fake(): FlowLabels.fake().labels}, LabelNames(())
    )
    store = FakeStatusStore(StateName("implementing"))
    refused = transition_with_fake_flow_labels(store, tracker, EventName("qa"), Force(False))
    _ = Assert.that(refused.error).is_instance(MissingFlowLabelsError)
    Assert.that(store.read().unwrap()).matches(StateName("implementing"))
    Assert.that(tracker.read_issue(IssueIdentifier.fake()).unwrap().labels).matches(LabelNames(()))


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
    Assert.that(TicketStatuses.fake().of(todo)).matches(todo_status)
    Assert.that(entering(tracker, todo, None, IssueStatusName.fake()).apply()).matches(Ok(None))
    issue = tracker.read_issue(IssueIdentifier.fake()).unwrap()
    Assert.that(issue.labels).matches(LabelNames((LabelName.fake(), LabelName(todo.root))))
    Assert.that(issue.status).matches(todo_status)


def test_reverting_the_flow_entry_restores_the_labels_and_status() -> None:
    held = LabelNames((LabelName.fake(),))
    tracker = seeded_tracker(held)
    maturing = IssueStatusName("Maturing")
    step = entering(tracker, StateName("todo"), None, maturing)
    _ = step.apply().unwrap()
    Assert.that(step.revert()).matches(Ok(None))
    issue = tracker.read_issue(IssueIdentifier.fake()).unwrap()
    Assert.that(issue.labels).matches(held)
    Assert.that(issue.status).matches(maturing)


def test_reverting_the_flow_entry_keeps_labels_added_since() -> None:
    tracker = seeded_tracker(LabelNames(()))
    step = entering(tracker, StateName("todo"), None, IssueStatusName("Maturing"))
    _ = step.apply().unwrap()
    added = LabelName.fake()
    tracker.add_label(IssueIdentifier.fake(), added).unwrap()
    _ = step.revert().unwrap()
    Assert.that(tracker.read_issue(IssueIdentifier.fake()).unwrap().labels).matches(
        LabelNames((added,))
    )


def test_reverting_the_flow_state_change_writes_back_the_replaced_flow_label() -> None:
    grill = StateName("grill")
    tracker = seeded_tracker(LabelNames((LabelName.fake(), LabelName(grill.root))))
    maturing = IssueStatusName("Maturing")
    step = entering(tracker, StateName("todo"), grill, maturing)
    _ = step.apply().unwrap()
    Assert.that(step.revert()).matches(Ok(None))
    issue = tracker.read_issue(IssueIdentifier.fake()).unwrap()
    Assert.that(issue.labels).matches(LabelNames((LabelName.fake(), LabelName(grill.root))))
    Assert.that(issue.status).matches(maturing)
