from mb_workflow.b_core.d_domain_model.clock import Today
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
from mb_workflow.c_infrastructure.linear import (
    CreatedAfter,
    CreatedWithin,
    IssuePage,
    IssueQuery,
    LabelKnown,
    LabelName,
    LabelNames,
    LabelPage,
    PageCursor,
    Project,
    StatusName,
)
from mb_workflow.c_infrastructure.shell import CommandOutput


def first_page() -> CommandOutput:
    return CommandOutput(
        """
        {
          "nodes": [
            {
              "identifier": "E-4289",
              "state": {"name": "Todo"},
              "project": {"name": "BE: Campaigns MVP"},
              "labels": {"nodes": [{"name": "d-implement"}]}
            }
          ],
          "pageInfo": {"hasNextPage": true, "endCursor": "17bec4c8-ce66-4546-a54f-aaefbc27e32f"}
        }
        """
    )


def last_page() -> CommandOutput:
    return CommandOutput(
        """
        {
          "nodes": [{"identifier": "E-4290", "state": {"name": "Backlog"}, "project": null}],
          "pageInfo": {"hasNextPage": false, "endCursor": "0030f372-5cc8-4492-bb3a-e27453b900d1"}
        }
        """
    )


def test_the_window_starts_the_lookback_before_today() -> None:
    assert CreatedAfter.of(CreatedWithin.fake(), Today.fake()) == CreatedAfter.fake()


def test_the_first_page_is_asked_for_without_a_cursor() -> None:
    assert IssueQuery.fake().command(None).root == (
        "linearis",
        "issues",
        "list",
        "--creator",
        "mab@flowbase.io",
        "--created-after",
        "2026-08-09",
        "--limit",
        "250",
    )


def test_a_later_page_is_asked_for_from_the_cursor() -> None:
    assert IssueQuery.fake().command(PageCursor.fake()).root[-2:] == (
        "--after",
        PageCursor.fake().root,
    )


def test_reads_the_issues_off_a_page() -> None:
    issues = IssuePage.parse(first_page()).issues()
    assert tuple(issue.identifier for issue in issues.root) == (IssueIdentifier.fake(),)


def test_reads_the_project_and_status_off_an_issue() -> None:
    issue = IssuePage.parse(first_page()).issues().root[0]
    assert (issue.status, issue.project) == (StatusName.fake(), Project.fake())


def test_reads_the_labels_an_issue_already_carries() -> None:
    assert IssuePage.parse(first_page()).issues().root[0].label_names() == LabelNames.fake()


def test_an_issue_without_a_project_carries_none() -> None:
    assert IssuePage.parse(last_page()).issues().root[0].project is None


def test_an_issue_without_labels_carries_none() -> None:
    assert IssuePage.parse(last_page()).issues().root[0].label_names() == LabelNames(())


def test_a_page_with_more_to_come_yields_the_next_cursor() -> None:
    assert IssuePage.parse(first_page()).next_cursor() == PageCursor.fake()


def test_the_last_page_yields_no_cursor_despite_reporting_one() -> None:
    assert IssuePage.parse(last_page()).next_cursor() is None


def label_page() -> CommandOutput:
    return CommandOutput(
        """
        {
          "nodes": [{"name": "Backend"}, {"name": "d-implement"}],
          "pageInfo": {"hasNextPage": false, "endCursor": "last"}
        }
        """
    )


def test_the_first_label_page_is_asked_for_without_a_cursor() -> None:
    assert LabelNames.lookup(None).root == ("linearis", "labels", "list", "--limit", "250")


def test_a_later_label_page_is_asked_for_from_the_cursor() -> None:
    assert LabelNames.lookup(PageCursor.fake()).root[-2:] == ("--after", PageCursor.fake().root)


def test_a_label_page_reports_whether_more_are_coming() -> None:
    assert LabelPage.parse(label_page()).next_cursor() is None


def test_finds_a_label_that_exists() -> None:
    assert LabelPage.parse(label_page()).names().has(LabelName.fake()) == LabelKnown(True)


def test_does_not_find_a_label_that_does_not_exist() -> None:
    assert LabelPage.parse(label_page()).names().has(LabelName("Frontend")) == LabelKnown(False)
