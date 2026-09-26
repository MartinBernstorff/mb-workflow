import logging
from typing import TYPE_CHECKING

import pytest

from mb_workflow.b_core.a_features.autolabel import (
    AutoLabelCriteria,
    AutolabelRequest,
    DryRun,
    ExcludePattern,
    Exclusions,
    Ledger,
    LedgerPath,
    LedgerText,
    Outcome,
    Recorded,
    Selection,
    SkipCount,
    SkipReason,
    UnknownLabelError,
    sweep,
)
from mb_workflow.b_core.c_secondary_ports.issue_tracker import FakeIssueTracker, TrackedIssue
from mb_workflow.b_core.d_domain_model.cache import CacheDirectory
from mb_workflow.b_core.d_domain_model.issue import (
    CreatedOn,
    Creator,
    Issue,
    IssueBody,
    IssueIdentifier,
    Issues,
    IssueTitle,
    LabelName,
    LabelNames,
    ProjectName,
    StatusName,
)
from mb_workflow.b_core.d_domain_model.outcome import Failed

if TYPE_CHECKING:
    from pathlib import Path


def default_issues() -> Issues:
    return Issues(
        (
            Issue(
                identifier=IssueIdentifier("E-1"),
                title=IssueTitle.fake(),
                body=IssueBody.fake(),
                status=StatusName("Todo"),
                project=ProjectName("BE: Campaigns MVP"),
                milestone=None,
                labels=LabelNames(()),
                assignee=None,
            ),
            Issue(
                identifier=IssueIdentifier("E-2"),
                title=IssueTitle.fake(),
                body=IssueBody.fake(),
                status=StatusName("Todo"),
                project=ProjectName("BE Shop"),
                milestone=None,
                labels=LabelNames(()),
                assignee=None,
            ),
            Issue(
                identifier=IssueIdentifier("E-3"),
                title=IssueTitle.fake(),
                body=IssueBody.fake(),
                status=StatusName("Todo"),
                project=ProjectName("Sentry Backend"),
                milestone=None,
                labels=LabelNames(()),
                assignee=None,
            ),
            Issue(
                identifier=IssueIdentifier("E-4"),
                title=IssueTitle.fake(),
                body=IssueBody.fake(),
                status=StatusName("Todo"),
                project=None,
                milestone=None,
                labels=LabelNames(()),
                assignee=None,
            ),
            Issue(
                identifier=IssueIdentifier("E-5"),
                title=IssueTitle.fake(),
                body=IssueBody.fake(),
                status=StatusName("Done"),
                project=ProjectName("Editor Bugs"),
                milestone=None,
                labels=LabelNames(()),
                assignee=None,
            ),
            Issue(
                identifier=IssueIdentifier("E-6"),
                title=IssueTitle.fake(),
                body=IssueBody.fake(),
                status=StatusName("Canceled"),
                project=ProjectName("Editor Bugs"),
                milestone=None,
                labels=LabelNames(()),
                assignee=None,
            ),
            Issue(
                identifier=IssueIdentifier("E-7"),
                title=IssueTitle.fake(),
                body=IssueBody.fake(),
                status=StatusName("Duplicate"),
                project=ProjectName("Editor Bugs"),
                milestone=None,
                labels=LabelNames(()),
                assignee=None,
            ),
            Issue(
                identifier=IssueIdentifier("E-8"),
                title=IssueTitle.fake(),
                body=IssueBody.fake(),
                status=StatusName("Triage"),
                project=ProjectName("Editor Bugs"),
                milestone=None,
                labels=LabelNames(()),
                assignee=None,
            ),
            Issue(
                identifier=IssueIdentifier("E-9"),
                title=IssueTitle.fake(),
                body=IssueBody.fake(),
                status=StatusName("Todo"),
                project=ProjectName("Editor Bugs"),
                milestone=None,
                labels=LabelNames.fake(),
                assignee=None,
            ),
            Issue(
                identifier=IssueIdentifier("E-10"),
                title=IssueTitle.fake(),
                body=IssueBody.fake(),
                status=StatusName("Todo"),
                project=ProjectName("Editor Bugs"),
                milestone=None,
                labels=LabelNames(()),
                assignee=None,
            ),
            Issue(
                identifier=IssueIdentifier("E-11"),
                title=IssueTitle.fake(),
                body=IssueBody.fake(),
                status=StatusName("Todo"),
                project=ProjectName("Editor Bugs"),
                milestone=None,
                labels=LabelNames(()),
                assignee=None,
            ),
        )
    )


def ledger() -> Ledger:
    return Ledger((IssueIdentifier("E-10"),))


def criteria() -> AutoLabelCriteria:
    return AutoLabelCriteria(label=LabelName.fake(), exclusions=Exclusions.fake(), ledger=ledger())


def selection() -> Selection:
    return Selection.of(default_issues(), criteria())


def chosen() -> tuple[IssueIdentifier, ...]:
    return tuple(issue.identifier for issue in selection().labellable().root)


def outcome() -> Outcome:
    return Outcome(selection=selection(), dry_run=DryRun(False), labelled=chosen(), failed=())


def dry_outcome() -> Outcome:
    return Outcome(selection=selection(), dry_run=DryRun(True), labelled=(), failed=())


def unexcluded() -> Selection:
    return Selection.of(
        default_issues(),
        AutoLabelCriteria(
            label=LabelName("Backend"),
            exclusions=Exclusions(projects=None, statuses=None),
            ledger=Ledger(()),
        ),
    )


def test_an_absent_pattern_excludes_nothing() -> None:
    assert unexcluded().labellable() == default_issues()


def test_a_project_matching_the_pattern_is_excluded() -> None:
    assert IssueIdentifier("E-1") not in chosen()


def test_the_pattern_is_unanchored_and_case_insensitive() -> None:
    assert ExcludePattern.fake().matches(ProjectName("Sentry Backend")).root


def test_a_project_the_pattern_misses_is_kept() -> None:
    assert not ExcludePattern.fake().matches(ProjectName("Editor Bugs")).root


def test_an_issue_with_no_project_is_labelled() -> None:
    assert IssueIdentifier("E-4") in chosen()


def test_every_excluded_status_is_dropped() -> None:
    dropped = (IssueIdentifier(f"E-{n}") for n in (5, 6, 7, 8))
    assert all(issue not in chosen() for issue in dropped)


def test_an_issue_already_carrying_the_label_is_skipped() -> None:
    assert IssueIdentifier("E-9") not in chosen()


def test_an_issue_in_the_ledger_is_skipped() -> None:
    assert IssueIdentifier("E-10") not in chosen()


def test_the_survivors_are_the_ones_nothing_excludes() -> None:
    assert chosen() == (IssueIdentifier("E-4"), IssueIdentifier("E-11"))


def test_counts_the_issues_dropped_for_each_reason() -> None:
    assert {tally.reason: tally.count.root for tally in selection().skips()} == {
        SkipReason.excluded_status: 4,
        SkipReason.excluded_project: 3,
        SkipReason.already_recorded: 1,
        SkipReason.already_labelled: 1,
    }


def test_a_run_that_labelled_everything_it_chose_exits_zero() -> None:
    assert outcome().failed_any() == Failed(False)


def test_a_run_with_a_failed_update_exits_non_zero() -> None:
    failed = outcome().model_copy(update={"failed": (IssueIdentifier("E-4"),)})
    assert failed.failed_any() == Failed(True)


def test_a_dry_run_exits_zero_because_it_attempted_nothing() -> None:
    assert dry_outcome().failed_any() == Failed(False)


def test_summarises_what_it_labelled_and_what_it_skipped() -> None:
    assert outcome().summary().root == (
        "Labelled 2 of 11 issues; skipped 4 excluded statuses, 3 excluded projects, "
        "1 already recorded, 1 already labelled"
    )


def test_a_dry_run_summarises_what_it_would_have_labelled() -> None:
    assert dry_outcome().summary().root.startswith("Would label 2 of 11 issues;")


def test_a_single_skip_is_counted_in_the_singular() -> None:
    assert SkipReason.excluded_project.counted(SkipCount(1)).root == "1 excluded project"


def test_several_skips_are_counted_in_the_plural() -> None:
    assert SkipReason.excluded_project.counted(SkipCount(2)).root == "2 excluded projects"


def test_a_plural_that_is_no_mere_suffix_is_spelled_out() -> None:
    assert SkipReason.excluded_status.counted(SkipCount(2)).root == "2 excluded statuses"


def test_a_reason_that_is_no_noun_reads_the_same_either_way() -> None:
    assert SkipReason.already_labelled.counted(SkipCount(2)).root == "2 already labelled"


def test_the_summary_names_the_updates_that_failed() -> None:
    failed = outcome().model_copy(update={"failed": (IssueIdentifier("E-4"),)})
    assert failed.summary().root.endswith("; 1 failed")


def test_a_sweep_that_skipped_nothing_summarises_only_the_labelling() -> None:
    every = unexcluded()
    labelled = tuple(issue.identifier for issue in every.labellable().root)
    every_outcome = Outcome(selection=every, dry_run=DryRun(False), labelled=labelled, failed=())
    assert every_outcome.summary().root == "Labelled 11 of 11 issues"


def test_a_dry_run_prints_a_line_per_issue_and_names_apply(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO):
        dry_outcome().report()
    assert "would label E-4" in caplog.text
    assert "would label E-11" in caplog.text
    assert "--apply" in caplog.text


def test_an_applied_run_prints_a_line_per_labelled_issue(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO):
        outcome().report()
    assert "labelled E-4" in caplog.text
    assert "--apply" not in caplog.text


def test_a_ledger_survives_a_round_trip_through_its_text() -> None:
    assert Ledger.decode(ledger().encode()) == ledger()


def test_an_empty_ledger_text_decodes_to_an_empty_ledger() -> None:
    assert Ledger.decode(LedgerText("")) == Ledger(())


def test_a_ledger_records_the_issues_it_was_extended_with() -> None:
    extended = ledger().extended(chosen())
    assert extended.records(IssueIdentifier("E-4")) == Recorded(True)


def test_a_ledger_does_not_record_an_issue_it_has_not_seen() -> None:
    assert ledger().records(IssueIdentifier("E-4")) == Recorded(False)


def test_a_missing_ledger_file_reads_as_empty(tmp_path: Path) -> None:
    path = LedgerPath.of(CacheDirectory(tmp_path), LabelName.fake())
    assert path.read() == Ledger(())


def test_a_written_ledger_reads_back(tmp_path: Path) -> None:
    path = LedgerPath.of(CacheDirectory(tmp_path), LabelName.fake())
    path.write(ledger().extended(chosen()))
    assert path.read() == ledger().extended(chosen())


def test_each_label_keeps_its_own_ledger(tmp_path: Path) -> None:
    directory = CacheDirectory(tmp_path)
    assert LedgerPath.of(directory, LabelName.fake()) != LedgerPath.of(
        directory, LabelName("Backend")
    )


def test_a_label_name_that_is_no_filename_still_gets_a_ledger(tmp_path: Path) -> None:
    path = LedgerPath.of(CacheDirectory(tmp_path), LabelName("BE: needs/triage"))
    path.write(ledger())
    assert path.read() == ledger()


def test_a_status_matching_the_pattern_is_excluded() -> None:
    assert Exclusions.fake().excludes_status(StatusName("Done")).root


def test_a_status_the_pattern_misses_is_kept() -> None:
    assert not Exclusions.fake().excludes_status(StatusName.fake()).root


def request_with(dry_run: DryRun) -> AutolabelRequest:
    return AutolabelRequest.fake().model_copy(update={"dry_run": dry_run})


def test_an_applied_sweep_labels_the_survivors_on_the_tracker(tmp_path: Path) -> None:
    tracker = FakeIssueTracker(
        LabelNames.fake(),
        tuple(
            TrackedIssue(issue=issue, creator=Creator.fake(), created_on=CreatedOn.fake())
            for issue in default_issues().root
        ),
    )
    _ = sweep(tracker, request_with(DryRun(False)), LedgerPath(tmp_path / "ledger.txt"))
    assert tracker.read_issue(IssueIdentifier("E-4")).labels == LabelNames.fake()


def test_an_applied_sweep_records_what_it_labelled(tmp_path: Path) -> None:
    tracker = FakeIssueTracker(
        LabelNames.fake(),
        tuple(
            TrackedIssue(issue=issue, creator=Creator.fake(), created_on=CreatedOn.fake())
            for issue in default_issues().root
        ),
    )
    ledger_path = LedgerPath(tmp_path / "ledger.txt")
    _ = sweep(tracker, request_with(DryRun(False)), ledger_path)
    assert ledger_path.read() == Ledger(tuple(IssueIdentifier(f"E-{n}") for n in (4, 10, 11)))


def test_a_dry_sweep_leaves_the_tracker_untouched(tmp_path: Path) -> None:
    tracker = FakeIssueTracker(
        LabelNames.fake(),
        tuple(
            TrackedIssue(issue=issue, creator=Creator.fake(), created_on=CreatedOn.fake())
            for issue in default_issues().root
        ),
    )
    _ = sweep(tracker, request_with(DryRun(True)), LedgerPath(tmp_path / "ledger.txt"))
    assert tracker.read_issue(IssueIdentifier("E-4")).labels == LabelNames(())


def test_sweeping_for_a_label_the_tracker_lacks_is_refused(tmp_path: Path) -> None:
    tracker = FakeIssueTracker(LabelNames.fake(), ())
    unknown = AutolabelRequest.fake().model_copy(update={"label": LabelName("Frontend")})
    with pytest.raises(UnknownLabelError, match="Frontend"):
        _ = sweep(tracker, unknown, LedgerPath(tmp_path / "ledger.txt"))
