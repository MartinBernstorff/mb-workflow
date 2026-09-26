from datetime import timedelta
from typing import override

import pytest

from mb_workflow.b_core.a_features.autolabel import (
    AutolabelRequest,
    DryRun,
    Outcome,
    UnknownLabelError,
    sweep,
)
from mb_workflow.b_core.c_secondary_ports.issue_tracker import (
    FakeIssueTracker,
    IssueTrackerError,
    TrackedIssue,
)
from mb_workflow.b_core.c_secondary_ports.ledger_store import FakeLedgerStore
from mb_workflow.b_core.d_domain_model.autolabel import Ledger, Recorded
from mb_workflow.b_core.d_domain_model.issue import (
    CreatedAfter,
    CreatedOn,
    Issue,
    IssueIdentifier,
    LabelName,
    LabelNames,
    ProjectName,
    StatusName,
)
from mb_workflow.b_core.d_domain_model.outcome import Failed


def tracked(identifier: IssueIdentifier, project: ProjectName) -> TrackedIssue:
    issue = Issue.fake().model_copy(
        update={
            "identifier": identifier,
            "status": StatusName("Todo"),
            "project": project,
            "labels": LabelNames(()),
        }
    )
    return TrackedIssue.fake().model_copy(update={"issue": issue})


def tracked_issues() -> tuple[TrackedIssue, ...]:
    editor = ProjectName("Editor Bugs")
    return (
        tracked(IssueIdentifier("E-1"), ProjectName("BE Shop")),
        tracked(IssueIdentifier("E-4"), editor),
        tracked(IssueIdentifier("E-10"), editor),
        tracked(IssueIdentifier("E-11"), editor),
    )


def tracker() -> FakeIssueTracker:
    return FakeIssueTracker(LabelNames.fake(), tracked_issues())


class RefusingTracker(FakeIssueTracker):
    def __init__(self, refused: IssueIdentifier) -> None:
        super().__init__(LabelNames.fake(), tracked_issues())
        self._refused = refused

    @override
    def add_label(self, issue: IssueIdentifier, label: LabelName) -> None:
        if issue == self._refused:
            raise IssueTrackerError(f"{issue.root} refused the label.")
        super().add_label(issue, label)


def ledgers() -> FakeLedgerStore:
    store = FakeLedgerStore()
    store.write(LabelName.fake(), Ledger((IssueIdentifier("E-10"),)))
    return store


def request_with(dry_run: DryRun) -> AutolabelRequest:
    return AutolabelRequest.fake().model_copy(update={"dry_run": dry_run})


def applied(issues: FakeIssueTracker, store: FakeLedgerStore) -> Outcome:
    return sweep(issues, store, request_with(DryRun(False)), CreatedAfter.fake())


def test_an_applied_sweep_labels_the_survivors_on_the_tracker() -> None:
    issues = tracker()
    _ = applied(issues, ledgers())
    assert issues.read_issue(IssueIdentifier("E-4")).labels == LabelNames.fake()


def test_an_applied_sweep_leaves_the_skipped_issues_unlabelled() -> None:
    issues = tracker()
    _ = applied(issues, ledgers())
    assert issues.read_issue(IssueIdentifier("E-1")).labels == LabelNames(())


def test_an_applied_sweep_records_what_it_labelled() -> None:
    store = ledgers()
    _ = applied(tracker(), store)
    assert store.read(LabelName.fake()) == Ledger(
        tuple(IssueIdentifier(f"E-{n}") for n in (10, 4, 11))
    )


def test_an_applied_sweep_that_labelled_everything_has_not_failed() -> None:
    assert applied(tracker(), ledgers()).failed_any() == Failed(False)


def test_a_sweep_with_a_refused_update_has_failed() -> None:
    assert applied(RefusingTracker(IssueIdentifier("E-4")), ledgers()).failed_any() == Failed(True)


def test_a_refused_update_is_left_out_of_the_ledger() -> None:
    store = ledgers()
    _ = applied(RefusingTracker(IssueIdentifier("E-4")), store)
    assert store.read(LabelName.fake()).records(IssueIdentifier("E-4")) == Recorded(False)


def test_a_dry_sweep_leaves_the_tracker_untouched() -> None:
    issues = tracker()
    _ = sweep(issues, ledgers(), request_with(DryRun(True)), CreatedAfter.fake())
    assert issues.read_issue(IssueIdentifier("E-4")).labels == LabelNames(())


def test_a_dry_sweep_leaves_the_ledger_untouched() -> None:
    store = ledgers()
    _ = sweep(tracker(), store, request_with(DryRun(True)), CreatedAfter.fake())
    assert store.read(LabelName.fake()) == Ledger((IssueIdentifier("E-10"),))


def test_a_sweep_leaves_issues_created_before_the_window_alone() -> None:
    issues = tracker()
    after = CreatedAfter(CreatedOn.fake().root + timedelta(days=1))
    _ = sweep(issues, ledgers(), request_with(DryRun(False)), after)
    assert issues.read_issue(IssueIdentifier("E-4")).labels == LabelNames(())


def test_sweeping_for_a_label_the_tracker_lacks_is_refused() -> None:
    unknown = AutolabelRequest.fake().model_copy(update={"label": LabelName("Frontend")})
    with pytest.raises(UnknownLabelError, match="Frontend"):
        _ = sweep(tracker(), ledgers(), unknown, CreatedAfter.fake())
