from safe_result import Err

from mb_workflow.b_core.a_features.create_ticket import TicketCreation
from mb_workflow.b_core.b_domain_services.flow_label_check import MissingFlowLabelsError
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
    FakeTicketTracker,
    TrackedIssue,
)
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
    StatusTypes,
)
from mb_workflow.b_core.d_domain_model.ticket_draft import TicketDefaults, TicketDraft
from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses


def blocker() -> TrackedIssue:
    return TrackedIssue.fake().model_copy(
        update={"issue": Issue.fake().model_copy(update={"identifier": IssueIdentifier("E-1")})}
    )


def tracking(groups: LabelNames = FlowLabels.fake().labels) -> FakeTicketTracker:
    return FakeTicketTracker(
        FlowLabels.fake().labels,
        (TrackedIssue.fake(), blocker()),
        Projects.fake(),
        IssueStatuses(
            (
                *IssueStatuses.fake().root,
                IssueStatus(name=IssueStatusName("Maturing"), type=StatusType.unstarted),
            )
        ),
        Assignee.fake(),
        groups={FlowLabels.fake().group: groups},
    )


def created(tracker: FakeTicketTracker, draft: TicketDraft) -> IssueIdentifier:
    return (
        TicketCreation.create_ticket(
            tracker=tracker,
            draft=draft,
            defaults=TicketDefaults.fake(),
            flow_labels=FlowLabels.fake(),
            statuses=TicketStatuses.fake(),
        )
        .unwrap()
        .identifier
    )


def test_a_created_ticket_starts_in_the_first_flow_state() -> None:
    tracker = tracking()
    issue = tracker.read_issue(created(tracker, TicketDraft.fake())).unwrap()
    assert (issue.labels, issue.status) == (
        LabelNames((LabelName("grill"),)),
        IssueStatusName("Maturing"),
    )


def test_a_created_ticket_is_related_to_the_issues_it_blocks_and_is_blocked_by() -> None:
    tracker = tracking()
    draft = TicketDraft.fake().model_copy(
        update={"blocks": (IssueIdentifier.fake(),), "blocked_by": (IssueIdentifier("E-1"),)}
    )
    identifier = created(tracker, draft)
    assert tracker.blockers(identifier).unwrap() == (IssueIdentifier("E-1"),)
    assert tracker.blockers(IssueIdentifier.fake()).unwrap() == (identifier,)


def test_a_relation_to_an_unknown_issue_is_refused_before_the_ticket_is_created() -> None:
    tracker = tracking()
    unknown = IssueIdentifier("E-404")
    draft = TicketDraft.fake().model_copy(update={"blocked_by": (unknown,)})
    refused = TicketCreation.create_ticket(
        tracker=tracker,
        draft=draft,
        defaults=TicketDefaults.fake(),
        flow_labels=FlowLabels.fake(),
        statuses=TicketStatuses.fake(),
    )
    assert isinstance(refused, Err)
    assert unknown.root in str(refused.error)
    assert tracker.labelled_issues(LabelName("grill"), StatusTypes(())).unwrap().root == ()


def test_creating_a_ticket_before_the_flow_labels_exist_is_refused() -> None:
    refused = TicketCreation.create_ticket(
        tracker=tracking(groups=LabelNames(())),
        draft=TicketDraft.fake(),
        defaults=TicketDefaults.fake(),
        flow_labels=FlowLabels.fake(),
        statuses=TicketStatuses.fake(),
    )
    assert isinstance(refused, Err)
    assert isinstance(refused.error, MissingFlowLabelsError)


def test_a_flow_label_passed_as_a_label_creates_no_ticket() -> None:
    tracker = tracking()
    draft = TicketDraft.fake().model_copy(update={"labels": LabelNames((LabelName("todo"),))})
    refused = TicketCreation.create_ticket(
        tracker=tracker,
        draft=draft,
        defaults=TicketDefaults.fake(),
        flow_labels=FlowLabels.fake(),
        statuses=TicketStatuses.fake(),
    )
    assert isinstance(refused, Err)
    assert tracker.labelled_issues(LabelName("grill"), StatusTypes(())).unwrap().root == ()
