from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING

import pytest

from mb_workflow.b_core.c_secondary_ports.issue_tracker import (
    FakeIssueTracker,
    IssueTrackerError,
    TrackedIssue,
)
from mb_workflow.b_core.d_domain_model.issue import (
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
from mb_workflow.c_infrastructure.linear import Linear
from mb_workflow.c_infrastructure.linearis_simulator import LinearisSimulator

if TYPE_CHECKING:
    from collections.abc import Callable

    from mb_workflow.b_core.c_secondary_ports.issue_tracker import IssueTracker

type Tracking = Callable[[LabelNames, tuple[TrackedIssue, ...]], IssueTracker]


def simulated(labels: LabelNames, issues: tuple[TrackedIssue, ...]) -> IssueTracker:
    return Linear(LinearisSimulator(labels, issues))


class TrackerKind(StrEnum):
    fake = "fake"
    linear = "linear"


@pytest.fixture(params=list(TrackerKind))
def tracking(request: pytest.FixtureRequest) -> Tracking:
    if TrackerKind(request.param) == TrackerKind.fake:
        return FakeIssueTracker
    return simulated


def workspace_labels() -> LabelNames:
    return LabelNames(tuple(LabelName(name) for name in ("Backend", "d-grill", "d-implement")))


def tracked(identifier: IssueIdentifier, creator: Creator, created: CreatedOn) -> TrackedIssue:
    return TrackedIssue(
        issue=Issue.fake().model_copy(update={"identifier": identifier, "labels": LabelNames(())}),
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
            ),
            creator=Creator.fake(),
            created_on=CreatedOn.fake(),
        ),
    )


def tracker(tracking: Tracking) -> IssueTracker:
    return tracking(workspace_labels(), backlog())


def test_every_workspace_label_is_listed_however_many_pages_it_spans(
    tracking: Tracking,
) -> None:
    assert tracker(tracking).labels() == workspace_labels()


def test_the_filter_picks_the_issues_one_creator_made_since_a_date(tracking: Tracking) -> None:
    swept = tracker(tracking).issues(IssueFilter.fake())
    assert swept.identifiers() == tuple(IssueIdentifier(f"E-{n}") for n in (1, 4, 5))


def test_the_filter_start_date_is_exclusive(tracking: Tracking) -> None:
    after = IssueFilter(creator=Creator.fake(), created_after=CreatedAfter(date(2026, 9, 1)))
    assert tracker(tracking).issues(after).identifiers() == (IssueIdentifier("E-4"),)


def test_reads_an_issue_back_as_it_was_given(tracking: Tracking) -> None:
    assert tracker(tracking).read(IssueIdentifier("E-5")) == backlog()[-1].issue


def test_an_issue_without_a_project_carries_none(tracking: Tracking) -> None:
    assert tracker(tracking).read(IssueIdentifier("E-5")).project is None


def test_reading_an_unknown_issue_is_refused(tracking: Tracking) -> None:
    with pytest.raises(IssueTrackerError):
        _ = tracker(tracking).read(IssueIdentifier("E-404"))


def test_an_added_label_joins_the_ones_already_there(tracking: Tracking) -> None:
    subject = tracker(tracking)
    subject.add_label(IssueIdentifier("E-5"), LabelName.fake())
    assert subject.read(IssueIdentifier("E-5")).labels == LabelNames(
        (LabelName("d-grill"), LabelName.fake())
    )


def test_adding_a_label_twice_carries_it_once(tracking: Tracking) -> None:
    subject = tracker(tracking)
    subject.add_label(IssueIdentifier("E-1"), LabelName.fake())
    subject.add_label(IssueIdentifier("E-1"), LabelName.fake())
    assert subject.read(IssueIdentifier("E-1")).labels == LabelNames.fake()


def test_adding_an_unknown_label_is_refused(tracking: Tracking) -> None:
    with pytest.raises(IssueTrackerError):
        tracker(tracking).add_label(IssueIdentifier("E-1"), LabelName("Frontend"))


def test_setting_labels_replaces_the_ones_there(tracking: Tracking) -> None:
    subject = tracker(tracking)
    subject.set_labels(IssueIdentifier("E-5"), LabelNames((LabelName("Backend"),)))
    assert subject.read(IssueIdentifier("E-5")).labels == LabelNames((LabelName("Backend"),))


def test_setting_no_labels_clears_them(tracking: Tracking) -> None:
    subject = tracker(tracking)
    subject.set_labels(IssueIdentifier("E-5"), LabelNames(()))
    assert subject.read(IssueIdentifier("E-5")).labels == LabelNames(())


def test_setting_an_unknown_label_is_refused(tracking: Tracking) -> None:
    with pytest.raises(IssueTrackerError):
        tracker(tracking).set_labels(IssueIdentifier("E-5"), LabelNames((LabelName("Frontend"),)))


def test_assigning_a_known_issue_succeeds(tracking: Tracking) -> None:
    tracker(tracking).assign(IssueIdentifier("E-1"), Assignee.fake())


def test_assigning_an_unknown_issue_is_refused(tracking: Tracking) -> None:
    with pytest.raises(IssueTrackerError):
        tracker(tracking).assign(IssueIdentifier("E-404"), Assignee.fake())


def test_a_project_survives_the_round_trip(tracking: Tracking) -> None:
    assert tracker(tracking).read(IssueIdentifier("E-1")).project == ProjectName.fake()
