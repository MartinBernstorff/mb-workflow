from mb_workflow.b_core.b_domain_services.label_selection import Selection
from mb_workflow.b_core.d_domain_model.autolabel import (
    AutoLabelCriteria,
    Exclusions,
    Ledger,
    SkipReason,
)
from mb_workflow.b_core.d_domain_model.issue import (
    Issue,
    IssueIdentifier,
    Issues,
    LabelName,
    LabelNames,
    ProjectName,
    StatusName,
)


def issue(
    identifier: IssueIdentifier,
    status: StatusName,
    project: ProjectName | None,
    labels: LabelNames = LabelNames(()),
) -> Issue:
    return Issue.fake().model_copy(
        update={"identifier": identifier, "status": status, "project": project, "labels": labels}
    )


def default_issues() -> Issues:
    todo = StatusName("Todo")
    editor = ProjectName("Editor Bugs")
    return Issues(
        (
            issue(IssueIdentifier("E-1"), todo, ProjectName("BE: Campaigns MVP")),
            issue(IssueIdentifier("E-2"), todo, ProjectName("BE Shop")),
            issue(IssueIdentifier("E-3"), todo, ProjectName("Sentry Backend")),
            issue(IssueIdentifier("E-4"), todo, None),
            issue(IssueIdentifier("E-5"), StatusName("Done"), editor),
            issue(IssueIdentifier("E-6"), StatusName("Canceled"), editor),
            issue(IssueIdentifier("E-7"), StatusName("Duplicate"), editor),
            issue(IssueIdentifier("E-8"), StatusName("Triage"), editor),
            issue(IssueIdentifier("E-9"), todo, editor, LabelNames.fake()),
            issue(IssueIdentifier("E-10"), todo, editor),
            issue(IssueIdentifier("E-11"), todo, editor),
        )
    )


def criteria() -> AutoLabelCriteria:
    return AutoLabelCriteria.fake().model_copy(
        update={"ledger": Ledger((IssueIdentifier("E-10"),))}
    )


def selection() -> Selection:
    return Selection.of(default_issues(), criteria())


def test_the_labellable_issues_are_the_ones_nothing_excludes() -> None:
    assert selection().labellable().identifiers() == (
        IssueIdentifier("E-4"),
        IssueIdentifier("E-11"),
    )


def test_counts_the_issues_dropped_for_each_reason() -> None:
    assert {tally.reason: tally.count.root for tally in selection().skips()} == {
        SkipReason.excluded_status: 4,
        SkipReason.excluded_project: 3,
        SkipReason.already_recorded: 1,
        SkipReason.already_labelled: 1,
    }


def test_a_selection_that_skipped_nothing_tallies_no_skips() -> None:
    unexcluded = AutoLabelCriteria(
        label=LabelName("Backend"),
        exclusions=Exclusions(projects=None, statuses=None),
        ledger=Ledger(()),
    )
    assert Selection.of(default_issues(), unexcluded).skips() == ()
