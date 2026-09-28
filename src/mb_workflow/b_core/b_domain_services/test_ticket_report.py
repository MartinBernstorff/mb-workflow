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
    assert TicketReport.of(IssueDetail.fake()).root == (
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
    assert TicketReport.of(bare).root == "E-4289 Add widget\nstatus: Todo\n"


def test_labels_are_joined_by_commas() -> None:
    labelled = IssueDetail.fake().model_copy(
        update={
            "issue": Issue.fake().model_copy(
                update={"labels": LabelNames((LabelName("Backend"), LabelName("d-grill")))}
            )
        }
    )
    assert "labels: Backend, d-grill\n" in TicketReport.of(labelled).root


def test_an_empty_description_reports_no_body() -> None:
    blank = IssueDetail.fake().model_copy(update={"description": IssueDescription("")})
    assert TicketReport.of(blank).root.endswith("labels: d-implement\n")


def test_relations_are_reported_after_the_labels_in_identifier_order() -> None:
    related = IssueDetail.fake().model_copy(
        update={
            "blocks": frozenset({IssueIdentifier("E-3"), IssueIdentifier("E-2")}),
            "blocked_by": frozenset({IssueIdentifier("E-1")}),
        }
    )
    assert "labels: d-implement\nblocks: E-2, E-3\nblocked by: E-1\n" in (
        TicketReport.of(related).root
    )
