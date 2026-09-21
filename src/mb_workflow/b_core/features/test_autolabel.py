import logging
from typing import TYPE_CHECKING

from mb_workflow.a_presentation.console import ExitCode
from mb_workflow.b_core.cache import CacheDirectory
from mb_workflow.b_core.features.autolabel import (
    Apply,
    Criteria,
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
)
from mb_workflow.b_core.issue import IssueIdentifier
from mb_workflow.c_infrastructure.linear import (
    IssuePage,
    LabelName,
    ListedIssues,
    ProjectName,
    StatusName,
)
from mb_workflow.c_infrastructure.shell import CommandOutput

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def swept() -> ListedIssues:
    return IssuePage.parse(
        CommandOutput(
            """
            {
              "nodes": [
                {"identifier": "E-1", "state": {"name": "Todo"},
                 "project": {"name": "BE: Campaigns MVP"}},
                {"identifier": "E-2", "state": {"name": "Todo"},
                 "project": {"name": "BE Shop"}},
                {"identifier": "E-3", "state": {"name": "Todo"},
                 "project": {"name": "Sentry Backend"}},
                {"identifier": "E-4", "state": {"name": "Todo"}, "project": null},
                {"identifier": "E-5", "state": {"name": "Done"},
                 "project": {"name": "Editor Bugs"}},
                {"identifier": "E-6", "state": {"name": "Canceled"},
                 "project": {"name": "Editor Bugs"}},
                {"identifier": "E-7", "state": {"name": "Duplicate"},
                 "project": {"name": "Editor Bugs"}},
                {"identifier": "E-8", "state": {"name": "Triage"},
                 "project": {"name": "Editor Bugs"}},
                {"identifier": "E-9", "state": {"name": "Todo"},
                 "project": {"name": "Editor Bugs"},
                 "labels": {"nodes": [{"name": "d-implement"}]}},
                {"identifier": "E-10", "state": {"name": "Todo"},
                 "project": {"name": "Editor Bugs"}},
                {"identifier": "E-11", "state": {"name": "Todo"},
                 "project": {"name": "Editor Bugs"}}
              ],
              "pageInfo": {"hasNextPage": false, "endCursor": "last"}
            }
            """
        )
    ).issues()


def ledger() -> Ledger:
    return Ledger((IssueIdentifier("E-10"),))


def criteria() -> Criteria:
    return Criteria(label=LabelName.fake(), exclusions=Exclusions.fake(), ledger=ledger())


def selection() -> Selection:
    return Selection.of(swept(), criteria())


def chosen() -> tuple[IssueIdentifier, ...]:
    return tuple(issue.identifier for issue in selection().labellable().root)


def outcome() -> Outcome:
    return Outcome(selection=selection(), applied=Apply(True), labelled=chosen(), failed=())


def dry_outcome() -> Outcome:
    return Outcome(selection=selection(), applied=Apply(False), labelled=(), failed=())


def unexcluded() -> Selection:
    return Selection.of(
        swept(),
        Criteria(
            label=LabelName("Backend"),
            exclusions=Exclusions(projects=None, statuses=None),
            ledger=Ledger(()),
        ),
    )


def test_an_absent_pattern_excludes_nothing() -> None:
    assert unexcluded().labellable() == swept()


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


def test_each_survivor_is_labelled_by_the_shared_command_builder() -> None:
    assert LabelName.fake().addition(chosen()[0]).root == (
        "linearis",
        "issues",
        "update",
        "E-4",
        "--labels",
        "d-implement",
        "--label-mode",
        "add",
    )


def test_counts_the_issues_dropped_for_each_reason() -> None:
    assert {tally.reason: tally.count.root for tally in selection().skips()} == {
        SkipReason.excluded_status: 4,
        SkipReason.excluded_project: 3,
        SkipReason.already_recorded: 1,
        SkipReason.already_labelled: 1,
    }


def test_a_run_that_labelled_everything_it_chose_exits_zero() -> None:
    assert outcome().exit_code() == ExitCode(0)


def test_a_run_with_a_failed_update_exits_non_zero() -> None:
    failed = outcome().model_copy(update={"failed": (IssueIdentifier("E-4"),)})
    assert failed.exit_code() == ExitCode(1)


def test_a_dry_run_exits_zero_because_it_attempted_nothing() -> None:
    assert dry_outcome().exit_code() == ExitCode(0)


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
    every_outcome = Outcome(selection=every, applied=Apply(True), labelled=labelled, failed=())
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
