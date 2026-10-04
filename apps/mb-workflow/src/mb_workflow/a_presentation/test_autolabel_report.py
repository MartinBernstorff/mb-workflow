import logging
from typing import TYPE_CHECKING

from assertions import Assert

from mb_workflow.a_presentation.autolabel_report import log_outcome, outcome_summary, skip_phrase
from mb_workflow.b_core.a_features.autolabel import DryRun, Outcome
from mb_workflow.b_core.b_domain_services.label_selection import Decision, Selection
from mb_workflow.b_core.d_domain_model.autolabel import SkipCount, SkipReason
from mb_workflow.b_core.d_domain_model.issue import Issue, IssueIdentifier

if TYPE_CHECKING:
    import pytest


def decision_for(identifier: IssueIdentifier, skipped: SkipReason | None) -> Decision:
    return Decision(
        issue=Issue.fake().model_copy(update={"identifier": identifier}), skipped=skipped
    )


def selection() -> Selection:
    return Selection(
        (
            decision_for(IssueIdentifier("E-1"), SkipReason.excluded_project),
            decision_for(IssueIdentifier("E-2"), SkipReason.excluded_project),
            decision_for(IssueIdentifier("E-3"), SkipReason.excluded_status),
            decision_for(IssueIdentifier("E-9"), SkipReason.already_labelled),
            decision_for(IssueIdentifier("E-10"), SkipReason.already_recorded),
            decision_for(IssueIdentifier("E-4"), None),
            decision_for(IssueIdentifier("E-11"), None),
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
    Assert.that(outcome_summary(outcome()).root).matches(
        "Labelled 2 of 7 issues; skipped 1 excluded status, 2 excluded projects, "
        "1 already recorded, 1 already labelled"
    )


def test_a_dry_run_summarises_what_it_would_have_labelled() -> None:
    Assert.that(outcome_summary(dry_outcome()).root).starts_with("Would label 2 of 7 issues;")


def test_the_summary_names_the_updates_that_failed() -> None:
    failed = outcome().model_copy(
        update={"labelled": (IssueIdentifier("E-11"),), "failed": (IssueIdentifier("E-4"),)}
    )
    Assert.that(outcome_summary(failed).root).ends_with("; 1 failed")


def test_a_sweep_that_skipped_nothing_summarises_only_the_labelling() -> None:
    every = Selection((decision_for(IssueIdentifier("E-4"), None),))
    labelled = Outcome(
        selection=every, dry_run=DryRun(False), labelled=(IssueIdentifier("E-4"),), failed=()
    )
    Assert.that(outcome_summary(labelled).root).matches("Labelled 1 of 1 issue")


def test_a_single_skip_is_counted_in_the_singular() -> None:
    Assert.that(skip_phrase(SkipReason.excluded_project, SkipCount(1)).root).matches(
        "1 excluded project"
    )


def test_several_skips_are_counted_in_the_plural() -> None:
    Assert.that(skip_phrase(SkipReason.excluded_project, SkipCount(2)).root).matches(
        "2 excluded projects"
    )


def test_a_plural_that_is_no_mere_suffix_is_spelled_out() -> None:
    Assert.that(skip_phrase(SkipReason.excluded_status, SkipCount(2)).root).matches(
        "2 excluded statuses"
    )


def test_a_reason_that_is_no_noun_reads_the_same_either_way() -> None:
    Assert.that(skip_phrase(SkipReason.already_labelled, SkipCount(2)).root).matches(
        "2 already labelled"
    )


def test_a_dry_run_prints_a_line_per_issue_and_names_apply(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO):
        log_outcome(dry_outcome())
    Assert.that(caplog.text).contains("would label E-4")
    Assert.that(caplog.text).contains("would label E-11")
    Assert.that(caplog.text).contains("--apply")


def test_an_applied_run_prints_a_line_per_labelled_issue(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO):
        log_outcome(outcome())
    Assert.that(caplog.text).contains("labelled E-4")
    Assert.that(caplog.text).not_().contains("--apply")
