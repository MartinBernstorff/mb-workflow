import logging
from typing import TYPE_CHECKING

from mb_workflow.a_presentation.autolabel_report import counted, report, summary
from mb_workflow.b_core.a_features.autolabel import DryRun, Outcome
from mb_workflow.b_core.b_domain_services.label_selection import Decision, Selection
from mb_workflow.b_core.d_domain_model.autolabel import SkipCount, SkipReason
from mb_workflow.b_core.d_domain_model.issue import Issue, IssueIdentifier

if TYPE_CHECKING:
    import pytest


def decided(identifier: IssueIdentifier, skipped: SkipReason | None) -> Decision:
    return Decision(
        issue=Issue.fake().model_copy(update={"identifier": identifier}), skipped=skipped
    )


def selection() -> Selection:
    return Selection(
        (
            decided(IssueIdentifier("E-1"), SkipReason.excluded_project),
            decided(IssueIdentifier("E-2"), SkipReason.excluded_project),
            decided(IssueIdentifier("E-3"), SkipReason.excluded_status),
            decided(IssueIdentifier("E-9"), SkipReason.already_labelled),
            decided(IssueIdentifier("E-10"), SkipReason.already_recorded),
            decided(IssueIdentifier("E-4"), None),
            decided(IssueIdentifier("E-11"), None),
        )
    )


def outcome() -> Outcome:
    return Outcome(
        selection=selection(),
        dry_run=DryRun(False),
        labelled=(IssueIdentifier("E-4"), IssueIdentifier("E-11")),
        failed=(),
    )


def dry_outcome() -> Outcome:
    return Outcome(selection=selection(), dry_run=DryRun(True), labelled=(), failed=())


def test_summarises_what_it_labelled_and_what_it_skipped() -> None:
    assert summary(outcome()).root == (
        "Labelled 2 of 7 issues; skipped 1 excluded status, 2 excluded projects, "
        "1 already recorded, 1 already labelled"
    )


def test_a_dry_run_summarises_what_it_would_have_labelled() -> None:
    assert summary(dry_outcome()).root.startswith("Would label 2 of 7 issues;")


def test_the_summary_names_the_updates_that_failed() -> None:
    failed = outcome().model_copy(
        update={"labelled": (IssueIdentifier("E-11"),), "failed": (IssueIdentifier("E-4"),)}
    )
    assert summary(failed).root.endswith("; 1 failed")


def test_a_sweep_that_skipped_nothing_summarises_only_the_labelling() -> None:
    every = Selection((decided(IssueIdentifier("E-4"), None),))
    labelled = Outcome(
        selection=every, dry_run=DryRun(False), labelled=(IssueIdentifier("E-4"),), failed=()
    )
    assert summary(labelled).root == "Labelled 1 of 1 issue"


def test_a_single_skip_is_counted_in_the_singular() -> None:
    assert counted(SkipReason.excluded_project, SkipCount(1)).root == "1 excluded project"


def test_several_skips_are_counted_in_the_plural() -> None:
    assert counted(SkipReason.excluded_project, SkipCount(2)).root == "2 excluded projects"


def test_a_plural_that_is_no_mere_suffix_is_spelled_out() -> None:
    assert counted(SkipReason.excluded_status, SkipCount(2)).root == "2 excluded statuses"


def test_a_reason_that_is_no_noun_reads_the_same_either_way() -> None:
    assert counted(SkipReason.already_labelled, SkipCount(2)).root == "2 already labelled"


def test_a_dry_run_prints_a_line_per_issue_and_names_apply(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO):
        report(dry_outcome())
    assert "would label E-4" in caplog.text
    assert "would label E-11" in caplog.text
    assert "--apply" in caplog.text


def test_an_applied_run_prints_a_line_per_labelled_issue(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO):
        report(outcome())
    assert "labelled E-4" in caplog.text
    assert "--apply" not in caplog.text
