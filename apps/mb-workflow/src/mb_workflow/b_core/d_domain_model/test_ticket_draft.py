from safe_result import Err, Result

from mb_workflow.b_core.d_domain_model.flow import StateName
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabelOptionError, FlowLabels
from mb_workflow.b_core.d_domain_model.issue import (
    Assignee,
    IssueDescription,
    IssueIdentifier,
    IssueStatusName,
    LabelName,
    LabelNames,
    Milestone,
    MilestoneName,
    NewIssue,
    ProjectName,
    TeamKey,
)
from mb_workflow.b_core.d_domain_model.ticket_draft import (
    TicketDefaults,
    TicketDraft,
    TicketDraftError,
)
from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses


def viewer() -> Assignee:
    return Assignee("viewer@flowbase.io")


def drafted(
    draft: TicketDraft, defaults: TicketDefaults = TicketDefaults.fake()
) -> Result[NewIssue, TicketDraftError | FlowLabelOptionError]:
    return draft.new_issue(
        defaults=defaults,
        start=StateName("grill"),
        flow_labels=FlowLabels.fake(),
        statuses=TicketStatuses.fake(),
        viewer=viewer(),
    )


def test_a_new_ticket_carries_the_flow_label_of_the_start_state() -> None:
    draft = TicketDraft.fake().model_copy(update={"labels": LabelNames((LabelName("Backend"),))})
    assert drafted(draft).unwrap().labels == LabelNames((LabelName("Backend"), LabelName("grill")))


def test_a_new_ticket_takes_the_status_mapped_to_the_start_state() -> None:
    assert drafted(TicketDraft.fake()).unwrap().status == IssueStatusName("Maturing")


def test_a_new_ticket_goes_to_the_configured_team_and_project() -> None:
    defaults = TicketDefaults(team=TeamKey("MB"), project=ProjectName("mb-workflow"))
    new = drafted(TicketDraft.fake(), defaults).unwrap()
    assert (new.team, new.project) == (TeamKey("MB"), ProjectName("mb-workflow"))


def test_a_named_project_overrides_the_configured_one() -> None:
    draft = TicketDraft.fake().model_copy(update={"project": ProjectName("Other")})
    assert drafted(draft).unwrap().project == ProjectName("Other")


def test_a_milestone_is_looked_up_in_the_ticket_project() -> None:
    draft = TicketDraft.fake().model_copy(update={"milestone": MilestoneName.fake()})
    assert drafted(draft).unwrap().milestone == Milestone(
        project=ProjectName.fake(), name=MilestoneName.fake()
    )


def test_a_milestone_without_a_project_is_refused() -> None:
    draft = TicketDraft.fake().model_copy(update={"milestone": MilestoneName.fake()})
    refused = drafted(draft, TicketDefaults(team=TeamKey("MB"), project=None))
    assert isinstance(refused, Err)
    assert isinstance(refused.error, TicketDraftError)


def test_me_assigns_the_viewer() -> None:
    draft = TicketDraft.fake().model_copy(update={"assignee": Assignee.me()})
    assert drafted(draft).unwrap().assignee == viewer()


def test_the_body_file_supplies_the_description() -> None:
    draft = TicketDraft.fake().model_copy(update={"body_file": IssueDescription.fake()})
    assert drafted(draft).unwrap().description == IssueDescription.fake()


def test_a_body_and_a_body_file_together_are_refused() -> None:
    draft = TicketDraft.fake().model_copy(
        update={"body": IssueDescription.fake(), "body_file": IssueDescription.fake()}
    )
    refused = drafted(draft)
    assert isinstance(refused, Err)
    assert isinstance(refused.error, TicketDraftError)


def test_the_blocking_relations_carry_over() -> None:
    draft = TicketDraft.fake().model_copy(
        update={"blocks": (IssueIdentifier("E-1"),), "blocked_by": (IssueIdentifier("E-2"),)}
    )
    new = drafted(draft).unwrap()
    assert (new.blocks, new.blocked_by) == ((IssueIdentifier("E-1"),), (IssueIdentifier("E-2"),))


def test_a_flow_label_among_the_labels_is_refused() -> None:
    draft = TicketDraft.fake().model_copy(update={"labels": LabelNames((LabelName("TODO"),))})
    state_option = "--state"
    refused = drafted(draft)
    assert isinstance(refused, Err)
    assert state_option in str(refused.error)
