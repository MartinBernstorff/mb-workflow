import pytest

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
    LabelName,
    LabelNames,
)


def seeded_tracker(held: LabelNames) -> FakeTicketTracker:
    wanted = FlowLabels.fake()
    issue = Issue.fake().model_copy(update={"labels": held})
    return FakeTicketTracker(
        LabelNames((*wanted.labels.root, LabelName.fake())),
        (TrackedIssue.fake().model_copy(update={"issue": issue}),),
        groups={wanted.group: wanted.labels},
    )


def transition_with_fake_flow_labels(
    store: FakeStatusStore, tracker: FakeTicketTracker, event: EventName, force: Force
) -> StateName:
    return transition(
        chart=WorkflowChart,
        store=store,
        tracker=tracker,
        issue=IssueIdentifier.fake(),
        wanted=FlowLabels.fake(),
        event=event,
        force=force,
    )


def test_a_legal_event_writes_the_target_state_to_the_store() -> None:
    store = FakeStatusStore(StateName("Implementing"))
    tracker = seeded_tracker(LabelNames(()))
    target = transition_with_fake_flow_labels(store, tracker, EventName("qa"), Force(False))
    assert target == StateName("QA")
    assert store.read() == StateName("QA")


def test_a_legal_event_writes_the_relabelled_labels_to_the_ticket() -> None:
    tracker = seeded_tracker(LabelNames((LabelName("Implementing"), LabelName.fake())))
    store = FakeStatusStore(StateName("Implementing"))
    _ = transition_with_fake_flow_labels(store, tracker, EventName("qa"), Force(False))
    assert tracker.read_issue(IssueIdentifier.fake()).labels == LabelNames(
        (LabelName.fake(), LabelName("QA"))
    )


def test_an_illegal_event_leaves_the_store_and_the_ticket_where_they_were() -> None:
    store = FakeStatusStore(StateName("Grilling"))
    tracker = seeded_tracker(LabelNames((LabelName("Grilling"),)))
    with pytest.raises(FlowError, match="merge is not legal from Grilling"):
        _ = transition_with_fake_flow_labels(store, tracker, EventName("merge"), Force(False))
    assert store.read() == StateName("Grilling")
    assert tracker.read_issue(IssueIdentifier.fake()).labels == LabelNames((LabelName("Grilling"),))


def test_forcing_writes_the_target_state_without_validating() -> None:
    store = FakeStatusStore(StateName("Grilling"))
    tracker = seeded_tracker(LabelNames(()))
    target = transition_with_fake_flow_labels(store, tracker, EventName("merged"), Force(True))
    assert target == StateName("Merged")
    assert store.read() == StateName("Merged")
    assert tracker.read_issue(IssueIdentifier.fake()).labels == LabelNames((LabelName("Merged"),))


def test_a_refused_ticket_write_leaves_the_board_where_it_was() -> None:
    wanted = FlowLabels.fake()
    store = FakeStatusStore(StateName("Implementing"))
    # The group lists the flow labels, but the workspace does not know them, so set_labels refuses.
    tracker = FakeTicketTracker(
        LabelNames.fake(), (TrackedIssue.fake(),), groups={wanted.group: wanted.labels}
    )
    with pytest.raises(TicketTrackerError, match="No label is named QA"):
        _ = transition_with_fake_flow_labels(store, tracker, EventName("qa"), Force(False))
    assert store.read() == StateName("Implementing")


def test_missing_flow_labels_point_to_seed_labels_and_leave_the_board_alone() -> None:
    store = FakeStatusStore(StateName("Implementing"))
    tracker = FakeTicketTracker(LabelNames.fake(), (TrackedIssue.fake(),))
    with pytest.raises(MissingFlowLabelsError, match="mw flow seed-labels"):
        _ = transition_with_fake_flow_labels(store, tracker, EventName("qa"), Force(False))
    assert store.read() == StateName("Implementing")
