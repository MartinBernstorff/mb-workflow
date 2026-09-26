from datetime import timedelta
from typing import override

import pytest

from mb_workflow.b_core.a_features.autolabel import (
    AutolabelRequest,
    DryRun,
    Outcome,
    UnknownLabelError,
    label_eligible_issues,
)
from mb_workflow.b_core.c_secondary_ports.ledger_store import FakeLedgerStore
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
    FakeTicketTracker,
    TicketTrackerError,
    TrackedIssue,
)
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


def unlabelled_tracked_issue(identifier: IssueIdentifier, project: ProjectName) -> TrackedIssue:
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
        unlabelled_tracked_issue(IssueIdentifier("E-1"), ProjectName("BE Shop")),
        unlabelled_tracked_issue(IssueIdentifier("E-4"), editor),
        unlabelled_tracked_issue(IssueIdentifier("E-10"), editor),
        unlabelled_tracked_issue(IssueIdentifier("E-11"), editor),
    )


def seeded_tracker() -> FakeTicketTracker:
    return FakeTicketTracker(LabelNames.fake(), tracked_issues())


class RefusingTracker(FakeTicketTracker):
    def __init__(self, refused: IssueIdentifier) -> None:
        super().__init__(LabelNames.fake(), tracked_issues())
        self._refused = refused

    @override
    def add_label(self, issue: IssueIdentifier, label: LabelName) -> None:
        if issue == self._refused:
            raise TicketTrackerError(f"{issue.root} refused the label.")
        super().add_label(issue, label)


def seeded_ledger_store() -> FakeLedgerStore:
    store = FakeLedgerStore()
    store.write(LabelName.fake(), Ledger((IssueIdentifier("E-10"),)))
    return store


def request_with(dry_run: DryRun) -> AutolabelRequest:
    return AutolabelRequest.fake().model_copy(update={"dry_run": dry_run})


def apply_labels(issues: FakeTicketTracker, store: FakeLedgerStore) -> Outcome:
    return label_eligible_issues(issues, store, request_with(DryRun(False)), CreatedAfter.fake())


def test_an_applied_sweep_labels_the_survivors_on_the_tracker() -> None:
    issues = seeded_tracker()
    _ = apply_labels(issues, seeded_ledger_store())
    assert issues.read_issue(IssueIdentifier("E-4")).labels == LabelNames.fake()


def test_an_applied_sweep_leaves_the_skipped_issues_unlabelled() -> None:
    issues = seeded_tracker()
    _ = apply_labels(issues, seeded_ledger_store())
    assert issues.read_issue(IssueIdentifier("E-1")).labels == LabelNames(())


def test_an_applied_sweep_records_what_it_labelled() -> None:
    store = seeded_ledger_store()
    _ = apply_labels(seeded_tracker(), store)
    assert store.read(LabelName.fake()) == Ledger(
        tuple(IssueIdentifier(f"E-{n}") for n in (10, 4, 11))
    )


def test_an_applied_sweep_that_labelled_everything_has_not_failed() -> None:
    assert apply_labels(seeded_tracker(), seeded_ledger_store()).failed_any() == Failed(False)


def test_a_sweep_with_a_refused_update_has_failed() -> None:
    assert apply_labels(
        RefusingTracker(IssueIdentifier("E-4")), seeded_ledger_store()
    ).failed_any() == Failed(True)


def test_a_refused_update_is_left_out_of_the_ledger() -> None:
    store = seeded_ledger_store()
    _ = apply_labels(RefusingTracker(IssueIdentifier("E-4")), store)
    assert store.read(LabelName.fake()).records(IssueIdentifier("E-4")) == Recorded(False)


def test_a_dry_sweep_leaves_the_tracker_untouched() -> None:
    issues = seeded_tracker()
    _ = label_eligible_issues(
        issues, seeded_ledger_store(), request_with(DryRun(True)), CreatedAfter.fake()
    )
    assert issues.read_issue(IssueIdentifier("E-4")).labels == LabelNames(())


def test_a_dry_sweep_leaves_the_ledger_untouched() -> None:
    store = seeded_ledger_store()
    _ = label_eligible_issues(
        seeded_tracker(), store, request_with(DryRun(True)), CreatedAfter.fake()
    )
    assert store.read(LabelName.fake()) == Ledger((IssueIdentifier("E-10"),))


def test_a_sweep_leaves_issues_created_before_the_window_alone() -> None:
    issues = seeded_tracker()
    after = CreatedAfter(CreatedOn.fake().root + timedelta(days=1))
    _ = label_eligible_issues(issues, seeded_ledger_store(), request_with(DryRun(False)), after)
    assert issues.read_issue(IssueIdentifier("E-4")).labels == LabelNames(())


def test_sweeping_for_a_label_the_tracker_lacks_is_refused() -> None:
    unknown = AutolabelRequest.fake().model_copy(update={"label": LabelName("Frontend")})
    with pytest.raises(UnknownLabelError, match="Frontend"):
        _ = label_eligible_issues(
            seeded_tracker(), seeded_ledger_store(), unknown, CreatedAfter.fake()
        )
