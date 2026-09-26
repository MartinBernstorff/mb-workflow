from mb_workflow.b_core.d_domain_model.autolabel import (
    AutoLabelCriteria,
    ExcludePattern,
    Exclusions,
    Ledger,
    Recorded,
    SkipReason,
)
from mb_workflow.b_core.d_domain_model.issue import (
    Issue,
    IssueIdentifier,
    LabelNames,
    ProjectName,
    StatusName,
)


def ledger() -> Ledger:
    return Ledger((IssueIdentifier("E-10"),))


def criteria() -> AutoLabelCriteria:
    return AutoLabelCriteria.fake().model_copy(update={"ledger": ledger()})


def unlabelled() -> Issue:
    return Issue.fake().model_copy(
        update={
            "identifier": IssueIdentifier("E-4"),
            "status": StatusName("Todo"),
            "project": ProjectName("Editor Bugs"),
            "labels": LabelNames(()),
        }
    )


def test_an_issue_nothing_excludes_is_not_skipped() -> None:
    assert criteria().skipped(unlabelled()) is None


def test_an_issue_with_no_project_is_not_skipped() -> None:
    assert criteria().skipped(unlabelled().model_copy(update={"project": None})) is None


def test_a_project_matching_the_pattern_is_skipped() -> None:
    issue = unlabelled().model_copy(update={"project": ProjectName("BE: Campaigns MVP")})
    assert criteria().skipped(issue) == SkipReason.excluded_project


def test_a_status_matching_the_pattern_is_skipped() -> None:
    issue = unlabelled().model_copy(update={"status": StatusName("Canceled")})
    assert criteria().skipped(issue) == SkipReason.excluded_status


def test_an_excluded_status_outranks_an_excluded_project() -> None:
    issue = unlabelled().model_copy(
        update={"status": StatusName("Done"), "project": ProjectName("BE Shop")}
    )
    assert criteria().skipped(issue) == SkipReason.excluded_status


def test_an_issue_in_the_ledger_is_skipped() -> None:
    issue = unlabelled().model_copy(update={"identifier": IssueIdentifier("E-10")})
    assert criteria().skipped(issue) == SkipReason.already_recorded


def test_an_issue_already_carrying_the_label_is_skipped() -> None:
    issue = unlabelled().model_copy(update={"labels": LabelNames.fake()})
    assert criteria().skipped(issue) == SkipReason.already_labelled


def test_an_absent_pattern_excludes_nothing() -> None:
    issue = unlabelled().model_copy(
        update={"status": StatusName("Done"), "project": ProjectName("BE Shop")}
    )
    unexcluded = criteria().model_copy(
        update={"exclusions": Exclusions(projects=None, statuses=None)}
    )
    assert unexcluded.skipped(issue) is None


def test_the_pattern_is_unanchored_and_case_insensitive() -> None:
    assert ExcludePattern.fake().matches(ProjectName("Sentry Backend")).root


def test_a_project_the_pattern_misses_is_kept() -> None:
    assert not ExcludePattern.fake().matches(ProjectName("Editor Bugs")).root


def test_a_ledger_records_the_issues_it_was_extended_with() -> None:
    extended = ledger().extended((IssueIdentifier("E-4"),))
    assert extended.records(IssueIdentifier("E-4")) == Recorded(True)


def test_a_ledger_does_not_record_an_issue_it_has_not_seen() -> None:
    assert ledger().records(IssueIdentifier("E-4")) == Recorded(False)


def test_extending_a_ledger_keeps_each_issue_once() -> None:
    extended = ledger().extended((IssueIdentifier("E-10"), IssueIdentifier("E-4")))
    assert extended == Ledger((IssueIdentifier("E-10"), IssueIdentifier("E-4")))
