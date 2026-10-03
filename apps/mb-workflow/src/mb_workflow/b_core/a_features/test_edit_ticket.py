from safe_result import Err

from mb_workflow.b_core.a_features.edit_ticket import TicketEditor
from mb_workflow.b_core.b_domain_services.flow_label_check import MissingFlowLabelsError
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
    assert (
        tracker.read_issue_detail(IssueIdentifier.fake()).unwrap().title == TicketEdit.fake().title
    )


def test_editing_a_ticket_self_assigns_with_me() -> None:
    tracker = tracking()
    edit = TicketEdit.nothing().model_copy(update={"add_assignee": Assignee.me()})
    _ = TicketEditor.apply_edit(
        tracker, IssueIdentifier.fake(), edit, FlowLabels.fake(), TicketStatuses.fake()
    ).unwrap()
    assert tracker.read_issue_detail(IssueIdentifier.fake()).unwrap().assignee == Assignee.fake()


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
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().labels == LabelNames(
        (LabelName("Backend"),)
    )


def test_editing_an_unknown_ticket_fails() -> None:
    refused = TicketEditor.apply_edit(
        tracking(),
        IssueIdentifier("E-404"),
        TicketEdit.fake(),
        FlowLabels.fake(),
        TicketStatuses.fake(),
    )
    assert isinstance(refused, Err)
    assert isinstance(refused.error, TicketTrackerError)


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


def in_grilling(groups: LabelNames = FlowLabels.fake().labels) -> FakeTicketTracker:
    flow = FlowLabels.fake()
    grilling = Issue.fake().model_copy(
        update={"labels": LabelNames((LabelName.fake(), LabelName("Grilling")))}
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
        groups={flow.group: groups},
    )


def test_a_ticket_jumps_to_a_state_the_chart_does_not_lead_to() -> None:
    tracker = in_grilling()
    merged = LabelName("Merged")
    done = IssueStatusName("Done")
    edit = TicketEdit.nothing().model_copy(update={"state": StateName("merged")})
    _ = TicketEditor.apply_edit(
        tracker, IssueIdentifier.fake(), edit, FlowLabels.fake(), TicketStatuses.fake()
    ).unwrap()
    issue = tracker.read_issue(IssueIdentifier.fake()).unwrap()
    assert (issue.labels, issue.status) == (LabelNames((LabelName.fake(), merged)), done)


def test_moving_a_ticket_keeps_its_labels_outside_the_flow() -> None:
    tracker = in_grilling()
    review = LabelName("Review")
    edit = TicketEdit.nothing().model_copy(update={"state": StateName(review.root)})
    _ = TicketEditor.apply_edit(
        tracker, IssueIdentifier.fake(), edit, FlowLabels.fake(), TicketStatuses.fake()
    ).unwrap()
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().labels == LabelNames(
        (LabelName.fake(), review)
    )


def test_an_unknown_state_leaves_the_ticket_unchanged() -> None:
    tracker = in_grilling()
    before = tracker.read_issue(IssueIdentifier.fake()).unwrap()
    edit = TicketEdit.nothing().model_copy(update={"state": StateName("Nowhere")})
    refused = TicketEditor.apply_edit(
        tracker, IssueIdentifier.fake(), edit, FlowLabels.fake(), TicketStatuses.fake()
    )
    assert isinstance(refused, Err)
    assert isinstance(refused.error, UnknownStateError)
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap() == before


def test_moving_a_ticket_without_seeded_flow_labels_leaves_it_unchanged() -> None:
    tracker = in_grilling(groups=LabelNames(()))
    before = tracker.read_issue(IssueIdentifier.fake()).unwrap()
    edit = TicketEdit.nothing().model_copy(update={"state": StateName.fake()})
    refused = TicketEditor.apply_edit(
        tracker, IssueIdentifier.fake(), edit, FlowLabels.fake(), TicketStatuses.fake()
    )
    assert isinstance(refused, Err)
    assert isinstance(refused.error, MissingFlowLabelsError)
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap() == before


def test_a_flow_label_passed_as_a_label_leaves_the_ticket_unchanged() -> None:
    tracker = tracking()
    before = tracker.read_issue(IssueIdentifier.fake()).unwrap()
    edit = TicketEdit.nothing().model_copy(
        update={"add_labels": LabelNames((LabelName("Specced"),))}
    )
    refused = TicketEditor.apply_edit(
        tracker, IssueIdentifier.fake(), edit, FlowLabels.fake(), TicketStatuses.fake()
    )
    assert isinstance(refused, Err)
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap() == before


def tracking_another_issue(other: IssueIdentifier) -> FakeTicketTracker:
    held = Issue.fake().model_copy(update={"identifier": other})
    return FakeTicketTracker(
        LabelNames.fake(),
        (TrackedIssue.fake(), TrackedIssue.fake().model_copy(update={"issue": held})),
        Projects.fake(),
        IssueStatuses.fake(),
        Assignee.fake(),
    )


def test_editing_a_ticket_adds_the_issues_it_blocks() -> None:
    blocked = IssueIdentifier("E-1")
    tracker = tracking_another_issue(blocked)
    edit = TicketEdit.nothing().model_copy(update={"add_blocks": (blocked,)})
    _ = TicketEditor.apply_edit(
        tracker, IssueIdentifier.fake(), edit, FlowLabels.fake(), TicketStatuses.fake()
    ).unwrap()
    assert tracker.blockers(blocked).unwrap() == (IssueIdentifier.fake(),)


def test_editing_a_ticket_adds_the_issues_it_is_blocked_by() -> None:
    blocker = IssueIdentifier("E-1")
    tracker = tracking_another_issue(blocker)
    edit = TicketEdit.nothing().model_copy(update={"add_blocked_by": (blocker,)})
    _ = TicketEditor.apply_edit(
        tracker, IssueIdentifier.fake(), edit, FlowLabels.fake(), TicketStatuses.fake()
    ).unwrap()
    assert tracker.blockers(IssueIdentifier.fake()).unwrap() == (blocker,)


def test_a_relation_to_an_unknown_issue_leaves_the_ticket_unchanged() -> None:
    tracker = tracking_another_issue(IssueIdentifier("E-1"))
    unknown = IssueIdentifier("E-404")
    before = tracker.read_issue_detail(IssueIdentifier.fake()).unwrap()
    edit = TicketEdit.fake().model_copy(update={"add_blocked_by": (unknown,)})
    refused = TicketEditor.apply_edit(
        tracker, IssueIdentifier.fake(), edit, FlowLabels.fake(), TicketStatuses.fake()
    )
    assert isinstance(refused, Err)
    assert unknown.root in str(refused.error)
    assert tracker.read_issue_detail(IssueIdentifier.fake()).unwrap() == before
