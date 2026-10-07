from assertions import Assert

from mb_workflow.b_core.b_domain_services.ticket_report import TicketReport
from mb_workflow.b_core.d_domain_model.issue import (
    Issue,
    IssueDescription,
    IssueDetail,
    IssueIdentifier,
    LabelName,
    LabelNames,
)


def test_reports_the_heading_the_fields_and_the_description() -> None:
    Assert.that(TicketReport.of(IssueDetail.fake()).root).matches(
        "E-4289 Add widget\n"
        "status: Todo\n"
        "project: BE: Campaigns MVP\n"
        "labels: d-implement\n"
        "\n"
        "The dashboard needs a widget.\n"
    )


def test_an_issue_without_a_project_labels_or_description_reports_none_of_them() -> None:
    bare = IssueDetail.fake().model_copy(
        update={
            "issue": Issue.fake().model_copy(update={"project": None, "labels": LabelNames(())}),
            "description": None,
        }
    )
    Assert.that(TicketReport.of(bare).root).matches("E-4289 Add widget\nstatus: Todo\n")


def test_labels_are_joined_by_commas() -> None:
    labelled = IssueDetail.fake().model_copy(
        update={
            "issue": Issue.fake().model_copy(
                update={"labels": LabelNames((LabelName("Backend"), LabelName("d-grill")))}
            )
        }
    )
    Assert.that(TicketReport.of(labelled).root).contains("labels: Backend, d-grill\n")


def test_an_empty_description_reports_no_body() -> None:
    blank = IssueDetail.fake().model_copy(update={"description": IssueDescription("")})
    Assert.that(TicketReport.of(blank).root).ends_with("labels: d-implement\n")


def test_relations_are_reported_after_the_labels_in_identifier_order() -> None:
    related = IssueDetail.fake().model_copy(
        update={
            "parent": IssueIdentifier("E-9"),
            "sub_tickets": frozenset({IssueIdentifier("E-8"), IssueIdentifier("E-7")}),
            "blocks": frozenset({IssueIdentifier("E-3"), IssueIdentifier("E-2")}),
            "blocked_by": frozenset({IssueIdentifier("E-1")}),
            "related": frozenset({IssueIdentifier("E-5"), IssueIdentifier("E-4")}),
        }
    )
    Assert.that(TicketReport.of(related).root).contains(
        "labels: d-implement\n"
        "parent: E-9\n"
        "sub-tickets: E-7, E-8\n"
        "blocks: E-2, E-3\n"
        "blocked by: E-1\n"
        "related: E-4, E-5\n"
    )
