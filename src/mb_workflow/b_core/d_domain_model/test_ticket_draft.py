import pytest

from mb_workflow.b_core.d_domain_model.flow import StateName
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
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


def drafted(draft: TicketDraft, defaults: TicketDefaults = TicketDefaults.fake()) -> NewIssue:
    return draft.new_issue(
        defaults=defaults,
        start=StateName("Grilling"),
        flow_labels=FlowLabels.fake(),
        statuses=TicketStatuses.fake(),
        viewer=viewer(),
    )


def test_a_new_ticket_carries_the_flow_label_of_the_start_state() -> None:
    draft = TicketDraft.fake().model_copy(update={"labels": LabelNames((LabelName("Backend"),))})
    assert drafted(draft).labels == LabelNames((LabelName("Backend"), LabelName("Grilling")))


def test_a_new_ticket_takes_the_status_mapped_to_the_start_state() -> None:
    assert drafted(TicketDraft.fake()).status == IssueStatusName("Maturing")


def test_a_new_ticket_goes_to_the_configured_team_and_project() -> None:
    defaults = TicketDefaults(team=TeamKey("MB"), project=ProjectName("mb-workflow"))
    new = drafted(TicketDraft.fake(), defaults)
    assert (new.team, new.project) == (TeamKey("MB"), ProjectName("mb-workflow"))


def test_a_named_project_overrides_the_configured_one() -> None:
    draft = TicketDraft.fake().model_copy(update={"project": ProjectName("Other")})
    assert drafted(draft).project == ProjectName("Other")


def test_a_milestone_is_looked_up_in_the_ticket_project() -> None:
    draft = TicketDraft.fake().model_copy(update={"milestone": MilestoneName.fake()})
    assert drafted(draft).milestone == Milestone(
        project=ProjectName.fake(), name=MilestoneName.fake()
    )


def test_a_milestone_without_a_project_is_refused() -> None:
    draft = TicketDraft.fake().model_copy(update={"milestone": MilestoneName.fake()})
    with pytest.raises(TicketDraftError, match="project"):
        _ = drafted(draft, TicketDefaults(team=TeamKey("MB"), project=None))


def test_me_assigns_the_viewer() -> None:
    draft = TicketDraft.fake().model_copy(update={"assignee": Assignee.me()})
    assert drafted(draft).assignee == viewer()


def test_the_body_file_supplies_the_description() -> None:
    draft = TicketDraft.fake().model_copy(update={"body_file": IssueDescription.fake()})
    assert drafted(draft).description == IssueDescription.fake()


def test_a_body_and_a_body_file_together_are_refused() -> None:
    draft = TicketDraft.fake().model_copy(
        update={"body": IssueDescription.fake(), "body_file": IssueDescription.fake()}
    )
    with pytest.raises(TicketDraftError, match="--body-file"):
        _ = drafted(draft)


def test_the_blocking_relations_carry_over() -> None:
    draft = TicketDraft.fake().model_copy(
        update={"blocks": (IssueIdentifier("E-1"),), "blocked_by": (IssueIdentifier("E-2"),)}
    )
    new = drafted(draft)
    assert (new.blocks, new.blocked_by) == ((IssueIdentifier("E-1"),), (IssueIdentifier("E-2"),))
