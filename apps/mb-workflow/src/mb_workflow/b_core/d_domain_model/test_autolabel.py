from assertions import Assert

from mb_workflow.b_core.d_domain_model.autolabel import (
    AutoLabelCriteria,
    ExcludePattern,
    Exclusions,
    Ledger,
    Recorded,
    SkipReason,
)
from mb_workflow.b_core.d_domain_model.issue import (
    GroupedLabel,
    GroupedLabels,
    Issue,
    IssueIdentifier,
    IssueStatusName,
    LabelGroupName,
    LabelName,
    LabelNames,
    ProjectName,
)


def ledger() -> Ledger:
    return Ledger((IssueIdentifier("E-10"),))


def criteria() -> AutoLabelCriteria:
    return AutoLabelCriteria.fake().model_copy(update={"ledger": ledger()})


def unlabelled() -> Issue:
    return Issue.fake().model_copy(
        update={
            "identifier": IssueIdentifier("E-4"),
            "status": IssueStatusName("Todo"),
            "project": ProjectName("Editor Bugs"),
            "labels": LabelNames(()),
        }
    )


def test_an_issue_nothing_excludes_is_not_skipped() -> None:
    Assert.that(criteria().skipped(unlabelled())).matches(None)


def test_an_issue_with_no_project_is_not_skipped() -> None:
    Assert.that(criteria().skipped(unlabelled().model_copy(update={"project": None}))).matches(None)


def test_a_project_matching_the_pattern_is_skipped() -> None:
    issue = unlabelled().model_copy(update={"project": ProjectName("BE: Campaigns MVP")})
    Assert.that(criteria().skipped(issue)).matches(SkipReason.excluded_project)


def test_a_status_matching_the_pattern_is_skipped() -> None:
    issue = unlabelled().model_copy(update={"status": IssueStatusName("Canceled")})
    Assert.that(criteria().skipped(issue)).matches(SkipReason.excluded_status)


def test_an_excluded_status_outranks_an_excluded_project() -> None:
    issue = unlabelled().model_copy(
        update={"status": IssueStatusName("Done"), "project": ProjectName("BE Shop")}
    )
    Assert.that(criteria().skipped(issue)).matches(SkipReason.excluded_status)


def test_an_issue_in_the_ledger_is_skipped() -> None:
    issue = unlabelled().model_copy(update={"identifier": IssueIdentifier("E-10")})
    Assert.that(criteria().skipped(issue)).matches(SkipReason.already_recorded)


def test_an_issue_already_carrying_the_label_is_skipped() -> None:
    issue = unlabelled().model_copy(update={"labels": LabelNames.fake()})
    Assert.that(criteria().skipped(issue)).matches(SkipReason.already_labelled)


def carrying(group: LabelGroupName) -> Issue:
    held = GroupedLabel(group=group, label=LabelName("frontend"))
    return unlabelled().model_copy(
        update={"labels": LabelNames((held.label,)), "grouped": GroupedLabels((held,))}
    )


def test_an_issue_carrying_another_label_of_the_group_is_skipped() -> None:
    Assert.that(criteria().skipped(carrying(LabelGroupName.fake()))).matches(
        SkipReason.labelled_in_group
    )


def test_a_label_of_another_group_does_not_skip_the_issue() -> None:
    Assert.that(criteria().skipped(carrying(LabelGroupName("area")))).matches(None)


def test_an_ungrouped_label_ignores_the_groups_an_issue_carries() -> None:
    ungrouped = criteria().model_copy(update={"group": None})
    Assert.that(ungrouped.skipped(carrying(LabelGroupName.fake()))).matches(None)


def test_an_absent_pattern_excludes_nothing() -> None:
    issue = unlabelled().model_copy(
        update={"status": IssueStatusName("Done"), "project": ProjectName("BE Shop")}
    )
    unexcluded = criteria().model_copy(
        update={"exclusions": Exclusions(projects=None, statuses=None)}
    )
    Assert.that(unexcluded.skipped(issue)).matches(None)


def test_the_pattern_is_unanchored_and_case_insensitive() -> None:
    Assert.that(ExcludePattern.fake().matches(ProjectName("Sentry Backend")).root).is_true()


def test_a_project_the_pattern_misses_is_kept() -> None:
    Assert.that(ExcludePattern.fake().matches(ProjectName("Editor Bugs")).root).is_false()


def test_a_ledger_records_the_issues_it_was_extended_with() -> None:
    extended = ledger().extended((IssueIdentifier("E-4"),))
    Assert.that(extended.records(IssueIdentifier("E-4"))).matches(Recorded(True))


def test_a_ledger_does_not_record_an_issue_it_has_not_seen() -> None:
    Assert.that(ledger().records(IssueIdentifier("E-4"))).matches(Recorded(False))


def test_extending_a_ledger_keeps_each_issue_once() -> None:
    extended = ledger().extended((IssueIdentifier("E-10"), IssueIdentifier("E-4")))
    Assert.that(extended).matches(Ledger((IssueIdentifier("E-10"), IssueIdentifier("E-4"))))
