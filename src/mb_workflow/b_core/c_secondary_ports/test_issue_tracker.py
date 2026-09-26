from datetime import date

import pytest

from mb_workflow.b_core.c_secondary_ports.issue_tracker import (
    FakeIssueTracker,
    IssueTrackerError,
    TrackedIssue,
)
from mb_workflow.b_core.d_domain_model.issue import (
    Assigned,
    Assignee,
    CreatedAfter,
    CreatedOn,
    Creator,
    Issue,
    IssueFilter,
    IssueIdentifier,
    LabelName,
    LabelNames,
    ProjectName,
    StatusName,
)


def workspace_labels() -> LabelNames:
    return LabelNames(tuple(LabelName(name) for name in ("Backend", "d-grill", "d-implement")))


def tracked(identifier: IssueIdentifier, creator: Creator, created: CreatedOn) -> TrackedIssue:
    return TrackedIssue(
        issue=Issue.fake().model_copy(
            update={"identifier": identifier, "labels": LabelNames(()), "assigned": Assigned(False)}
        ),
        creator=creator,
        created_on=created,
    )


def backlog() -> tuple[TrackedIssue, ...]:
    return (
        tracked(IssueIdentifier("E-1"), Creator("mab@flowbase.io"), CreatedOn(date(2026, 9, 1))),
        tracked(
            IssueIdentifier("E-2"), Creator("someone@flowbase.io"), CreatedOn(date(2026, 9, 1))
        ),
        tracked(IssueIdentifier("E-3"), Creator("mab@flowbase.io"), CreatedOn(date(2026, 8, 1))),
        tracked(IssueIdentifier("E-4"), Creator("mab@flowbase.io"), CreatedOn(date(2026, 9, 2))),
        TrackedIssue(
            issue=Issue(
                identifier=IssueIdentifier("E-5"),
                status=StatusName("Done"),
                project=None,
                labels=LabelNames((LabelName("d-grill"),)),
                assigned=Assigned(False),
            ),
            creator=Creator.fake(),
            created_on=CreatedOn.fake(),
        ),
    )


@pytest.fixture
def tracker() -> FakeIssueTracker:
    return FakeIssueTracker(workspace_labels(), backlog())


def test_every_workspace_label_is_listed(tracker: FakeIssueTracker) -> None:
    assert tracker.workspace_labels() == workspace_labels()


def test_the_filter_picks_the_issues_one_creator_made_since_a_date(
    tracker: FakeIssueTracker,
) -> None:
    swept = tracker.issues(IssueFilter.fake())
    assert swept.identifiers() == tuple(IssueIdentifier(f"E-{n}") for n in (1, 4, 5))


def test_the_filter_start_date_is_inclusive(tracker: FakeIssueTracker) -> None:
    after = IssueFilter(creator=Creator.fake(), created_after=CreatedAfter(date(2026, 9, 2)))
    assert tracker.issues(after).identifiers() == (IssueIdentifier("E-4"),)


def test_reads_an_issue_back_as_it_was_given(tracker: FakeIssueTracker) -> None:
    assert tracker.read(IssueIdentifier("E-5")) == backlog()[-1].issue


def test_an_issue_without_a_project_carries_none(tracker: FakeIssueTracker) -> None:
    assert tracker.read(IssueIdentifier("E-5")).project is None


def test_reading_an_unknown_issue_is_refused(tracker: FakeIssueTracker) -> None:
    with pytest.raises(IssueTrackerError):
        _ = tracker.read(IssueIdentifier("E-404"))


def test_an_added_label_joins_the_ones_already_there(tracker: FakeIssueTracker) -> None:
    tracker.add_label(IssueIdentifier("E-5"), LabelName.fake())
    assert tracker.read(IssueIdentifier("E-5")).labels == LabelNames(
        (LabelName("d-grill"), LabelName.fake())
    )


def test_adding_a_label_twice_carries_it_once(tracker: FakeIssueTracker) -> None:
    tracker.add_label(IssueIdentifier("E-1"), LabelName.fake())
    tracker.add_label(IssueIdentifier("E-1"), LabelName.fake())
    assert tracker.read(IssueIdentifier("E-1")).labels == LabelNames.fake()


def test_adding_an_unknown_label_is_refused(tracker: FakeIssueTracker) -> None:
    with pytest.raises(IssueTrackerError):
        tracker.add_label(IssueIdentifier("E-1"), LabelName("Frontend"))


def test_setting_labels_replaces_the_ones_there(tracker: FakeIssueTracker) -> None:
    tracker.set_labels(IssueIdentifier("E-5"), LabelNames((LabelName("Backend"),)))
    assert tracker.read(IssueIdentifier("E-5")).labels == LabelNames((LabelName("Backend"),))


def test_setting_no_labels_clears_them(tracker: FakeIssueTracker) -> None:
    tracker.set_labels(IssueIdentifier("E-5"), LabelNames(()))
    assert tracker.read(IssueIdentifier("E-5")).labels == LabelNames(())


def test_setting_an_unknown_label_is_refused(tracker: FakeIssueTracker) -> None:
    with pytest.raises(IssueTrackerError):
        tracker.set_labels(IssueIdentifier("E-5"), LabelNames((LabelName("Frontend"),)))


def test_an_issue_starts_unassigned(tracker: FakeIssueTracker) -> None:
    assert tracker.read(IssueIdentifier("E-1")).assigned == Assigned(False)


def test_assigning_an_issue_leaves_it_assigned(tracker: FakeIssueTracker) -> None:
    tracker.assign(IssueIdentifier("E-1"), Assignee.fake())
    assert tracker.read(IssueIdentifier("E-1")).assigned == Assigned(True)


def test_assigning_an_unknown_issue_is_refused(tracker: FakeIssueTracker) -> None:
    with pytest.raises(IssueTrackerError):
        tracker.assign(IssueIdentifier("E-404"), Assignee.fake())


def test_a_project_survives_the_round_trip(tracker: FakeIssueTracker) -> None:
    assert tracker.read(IssueIdentifier("E-1")).project == ProjectName.fake()


def test_a_label_is_found_whatever_its_case(tracker: FakeIssueTracker) -> None:
    tracker.add_label(IssueIdentifier("E-1"), LabelName("D-IMPLEMENT"))
    assert tracker.read(IssueIdentifier("E-1")).labels == LabelNames.fake()


def test_setting_labels_takes_the_workspace_spelling(tracker: FakeIssueTracker) -> None:
    tracker.set_labels(IssueIdentifier("E-1"), LabelNames((LabelName("backend"),)))
    assert tracker.read(IssueIdentifier("E-1")).labels == LabelNames((LabelName("Backend"),))


def test_adding_a_label_in_another_case_carries_it_once(tracker: FakeIssueTracker) -> None:
    tracker.add_label(IssueIdentifier("E-1"), LabelName.fake())
    tracker.add_label(IssueIdentifier("E-1"), LabelName("D-Implement"))
    assert tracker.read(IssueIdentifier("E-1")).labels == LabelNames.fake()
