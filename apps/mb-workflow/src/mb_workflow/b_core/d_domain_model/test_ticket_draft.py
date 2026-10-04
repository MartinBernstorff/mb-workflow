from typing import TYPE_CHECKING

from assertions import Assert

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
    Priority,
    ProjectName,
    TeamKey,
)
from mb_workflow.b_core.d_domain_model.ticket_draft import (
    TicketDefaults,
    TicketDraft,
    TicketDraftError,
)
from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses

if TYPE_CHECKING:
    from safe_result import Result


class GrillDraft:
    @staticmethod
    def viewer() -> Assignee:
        return Assignee("viewer@flowbase.io")

    @staticmethod
    def new_issue(
        draft: TicketDraft, defaults: TicketDefaults = TicketDefaults.fake()
    ) -> Result[NewIssue, TicketDraftError | FlowLabelOptionError]:
        return draft.new_issue(
            defaults=defaults,
            start=StateName("grill"),
            flow_labels=FlowLabels.fake(),
            statuses=TicketStatuses.fake(),
            viewer=GrillDraft.viewer(),
        )


def test_a_new_ticket_carries_the_flow_label_of_the_start_state() -> None:
    backend = LabelName("Backend")
    draft = TicketDraft.fake().model_copy(update={"labels": LabelNames((backend,))})
    Assert.that(GrillDraft.new_issue(draft).unwrap().labels).matches(
        LabelNames((backend, LabelName("grill")))
    )


def test_a_new_ticket_takes_the_status_mapped_to_the_start_state() -> None:
    maturing = IssueStatusName("Maturing")
    Assert.that(GrillDraft.new_issue(TicketDraft.fake()).unwrap().status).matches(maturing)


def test_a_new_ticket_goes_to_the_configured_team_and_project() -> None:
    team = TeamKey("MB")
    project = ProjectName("mb-workflow")
    defaults = TicketDefaults(team=team, project=project)
    new = GrillDraft.new_issue(TicketDraft.fake(), defaults).unwrap()
    Assert.that((new.team, new.project)).matches((team, project))


def test_a_named_project_overrides_the_configured_one() -> None:
    project = ProjectName("Other")
    draft = TicketDraft.fake().model_copy(update={"project": project})
    Assert.that(GrillDraft.new_issue(draft).unwrap().project).matches(project)


def test_a_milestone_is_looked_up_in_the_ticket_project() -> None:
    draft = TicketDraft.fake().model_copy(update={"milestone": MilestoneName.fake()})
    Assert.that(GrillDraft.new_issue(draft).unwrap().milestone).matches(
        Milestone(project=ProjectName.fake(), name=MilestoneName.fake())
    )


def test_a_milestone_without_a_project_is_refused() -> None:
    draft = TicketDraft.fake().model_copy(update={"milestone": MilestoneName.fake()})
    refused = GrillDraft.new_issue(draft, TicketDefaults(team=TeamKey("MB"), project=None))
    _ = Assert.that(refused.error).is_instance(TicketDraftError)


def test_me_assigns_the_viewer() -> None:
    draft = TicketDraft.fake().model_copy(update={"assignee": Assignee.me()})
    Assert.that(GrillDraft.new_issue(draft).unwrap().assignee).matches(GrillDraft.viewer())


def test_the_body_file_supplies_the_description() -> None:
    draft = TicketDraft.fake().model_copy(update={"body_file": IssueDescription.fake()})
    Assert.that(GrillDraft.new_issue(draft).unwrap().description).matches(IssueDescription.fake())


def test_a_body_and_a_body_file_together_are_refused() -> None:
    draft = TicketDraft.fake().model_copy(
        update={"body": IssueDescription.fake(), "body_file": IssueDescription.fake()}
    )
    refused = GrillDraft.new_issue(draft)
    _ = Assert.that(refused.error).is_instance(TicketDraftError)


def test_the_blocking_relations_carry_over() -> None:
    blocks = (IssueIdentifier("E-1"),)
    blocked_by = (IssueIdentifier("E-2"),)
    draft = TicketDraft.fake().model_copy(update={"blocks": blocks, "blocked_by": blocked_by})
    new = GrillDraft.new_issue(draft).unwrap()
    Assert.that((new.blocks, new.blocked_by)).matches((blocks, blocked_by))


def test_a_flow_label_among_the_labels_is_refused() -> None:
    draft = TicketDraft.fake().model_copy(update={"labels": LabelNames((LabelName("TODO"),))})
    state_option = "--state"
    refused = GrillDraft.new_issue(draft)
    error = Assert.that(refused.error).is_instance(FlowLabelOptionError)
    Assert.that(str(error)).contains(state_option)


def test_the_priority_carries_over() -> None:
    high = Priority.high
    draft = TicketDraft.fake().model_copy(update={"priority": high})
    Assert.that(GrillDraft.new_issue(draft).unwrap().priority).matches(high)


def test_a_ticket_without_a_priority_leaves_it_unset() -> None:
    Assert.that(GrillDraft.new_issue(TicketDraft.fake()).unwrap().priority).matches(None)
