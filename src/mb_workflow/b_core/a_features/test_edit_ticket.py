import pytest
from safe_result import Err

from mb_workflow.b_core.a_features.edit_ticket import TicketEditor
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
    FakeTicketTracker,
    TicketTrackerError,
    TrackedIssue,
)
from mb_workflow.b_core.d_domain_model.flow import StateName, UnknownStateError
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
from mb_workflow.b_core.d_domain_model.issue import (
    Assignee,
    Issue,
    IssueIdentifier,
    IssueStatus,
    IssueStatuses,
    IssueStatusName,
    LabelName,
    LabelNames,
    Projects,
    StatusType,
)
from mb_workflow.b_core.d_domain_model.ticket_edit import TicketEdit, TicketEditError
from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses


def tracking() -> FakeTicketTracker:
    return FakeTicketTracker(
        LabelNames((LabelName.fake(), LabelName("Backend"))),
        (TrackedIssue.fake(),),
        Projects.fake(),
        IssueStatuses.fake(),
        Assignee.fake(),
    )


def test_editing_a_ticket_writes_the_title() -> None:
    tracker = tracking()
    _ = TicketEditor.apply_edit(
        tracker, IssueIdentifier.fake(), TicketEdit.fake(), FlowLabels.fake(), TicketStatuses.fake()
    ).unwrap()
    assert tracker.read_issue_detail(IssueIdentifier.fake()).title == TicketEdit.fake().title


def test_editing_a_ticket_self_assigns_with_me() -> None:
    tracker = tracking()
    edit = TicketEdit.nothing().model_copy(update={"add_assignee": Assignee.me()})
    _ = TicketEditor.apply_edit(
        tracker, IssueIdentifier.fake(), edit, FlowLabels.fake(), TicketStatuses.fake()
    ).unwrap()
    assert tracker.read_issue_detail(IssueIdentifier.fake()).assignee == Assignee.fake()


def test_editing_a_ticket_swaps_labels() -> None:
    tracker = tracking()
    edit = TicketEdit.nothing().model_copy(
        update={
            "add_labels": LabelNames((LabelName("Backend"),)),
            "remove_labels": LabelNames.fake(),
        }
    )
    _ = TicketEditor.apply_edit(
        tracker, IssueIdentifier.fake(), edit, FlowLabels.fake(), TicketStatuses.fake()
    ).unwrap()
    assert tracker.read_issue(IssueIdentifier.fake()).labels == LabelNames((LabelName("Backend"),))


def test_editing_an_unknown_ticket_fails() -> None:
    with pytest.raises(TicketTrackerError):
        _ = TicketEditor.apply_edit(
            tracking(),
            IssueIdentifier("E-404"),
            TicketEdit.fake(),
            FlowLabels.fake(),
            TicketStatuses.fake(),
        )


def test_an_empty_edit_is_refused_before_the_ticket_is_read() -> None:
    refused = TicketEditor.apply_edit(
        tracking(),
        IssueIdentifier("E-404"),
        TicketEdit.nothing(),
        FlowLabels.fake(),
        TicketStatuses.fake(),
    )
    assert isinstance(refused, Err)
    assert isinstance(refused.error, TicketEditError)


def in_grilling() -> FakeTicketTracker:
    flow = FlowLabels.fake()
    grilling = Issue.fake().model_copy(
        update={
            "labels": LabelNames((LabelName.fake(), LabelName("Grilling"))),
            "status": IssueStatusName("Maturing"),
        }
    )
    return FakeTicketTracker(
        LabelNames((LabelName.fake(), *flow.labels.root)),
        (TrackedIssue.fake().model_copy(update={"issue": grilling}),),
        Projects.fake(),
        IssueStatuses(
            tuple(
                IssueStatus(name=status, type=StatusType.started)
                for status in TicketStatuses.fake().root.values()
            )
        ),
        Assignee.fake(),
        groups={flow.group: flow.labels},
    )


def moved(tracker: FakeTicketTracker, state: StateName) -> Issue:
    edit = TicketEdit.nothing().model_copy(update={"state": state})
    _ = TicketEditor.apply_edit(
        tracker, IssueIdentifier.fake(), edit, FlowLabels.fake(), TicketStatuses.fake()
    ).unwrap()
    return tracker.read_issue(IssueIdentifier.fake())


def test_a_ticket_jumps_to_a_state_the_chart_does_not_lead_to() -> None:
    merged = StateName("Merged")
    issue = moved(in_grilling(), StateName("merged"))
    assert (LabelName(merged.root) in issue.labels.root, issue.status) == (
        True,
        TicketStatuses.fake().of(merged),
    )


def test_moving_a_ticket_keeps_its_labels_outside_the_flow() -> None:
    issue = moved(in_grilling(), StateName("Review"))
    assert issue.labels == LabelNames((LabelName.fake(), LabelName("Review")))


def test_an_unknown_state_leaves_the_ticket_unchanged() -> None:
    tracker = in_grilling()
    before = tracker.read_issue(IssueIdentifier.fake())
    edit = TicketEdit.nothing().model_copy(update={"state": StateName("Nowhere")})
    refused = TicketEditor.apply_edit(
        tracker, IssueIdentifier.fake(), edit, FlowLabels.fake(), TicketStatuses.fake()
    )
    assert isinstance(refused, Err)
    assert isinstance(refused.error, UnknownStateError)
    assert tracker.read_issue(IssueIdentifier.fake()) == before


def test_a_flow_label_passed_as_a_label_leaves_the_ticket_unchanged() -> None:
    tracker = tracking()
    before = tracker.read_issue(IssueIdentifier.fake())
    edit = TicketEdit.nothing().model_copy(
        update={"add_labels": LabelNames((LabelName("Specced"),))}
    )
    refused = TicketEditor.apply_edit(
        tracker, IssueIdentifier.fake(), edit, FlowLabels.fake(), TicketStatuses.fake()
    )
    assert isinstance(refused, Err)
    assert tracker.read_issue(IssueIdentifier.fake()) == before
