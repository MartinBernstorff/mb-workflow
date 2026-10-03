import pytest

from mb_workflow.b_core.a_features.seed_labels import CoveredByWorkspace, seed_flow_labels
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
    FakeTicketTracker,
    TicketTrackerError,
)
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
from mb_workflow.b_core.d_domain_model.issue import LabelName, LabelNames, Team, TeamKey, TeamName


def other_team() -> Team:
    return Team(key=TeamKey("OPS"), name=TeamName("Operations"), projects=())


def empty_tracker() -> FakeTicketTracker:
    return FakeTicketTracker(LabelNames(()), (), teams=(Team.fake(), other_team()))


def test_seeding_creates_every_flow_label_in_the_team() -> None:
    tracker = empty_tracker()
    _ = seed_flow_labels(tracker, FlowLabels.fake(), TeamName.fake())
    assert tracker.group_labels(FlowLabels.fake().group, TeamKey.fake()) == FlowLabels.fake().labels


def test_seeding_a_team_creates_no_workspace_labels() -> None:
    tracker = empty_tracker()
    _ = seed_flow_labels(tracker, FlowLabels.fake(), TeamName.fake())
    assert tracker.group_labels(FlowLabels.fake().group, None) == LabelNames(())


def test_seeding_a_team_leaves_other_teams_without_flow_labels() -> None:
    tracker = empty_tracker()
    _ = seed_flow_labels(tracker, FlowLabels.fake(), TeamName.fake())
    assert tracker.group_labels(FlowLabels.fake().group, other_team().key) == LabelNames(())


def test_seeding_finds_the_team_whatever_the_case_of_its_name() -> None:
    tracker = empty_tracker()
    _ = seed_flow_labels(tracker, FlowLabels.fake(), TeamName(TeamName.fake().root.upper()))
    assert tracker.group_labels(FlowLabels.fake().group, TeamKey.fake()) == FlowLabels.fake().labels


def test_seeding_reports_the_labels_it_created() -> None:
    created = seed_flow_labels(empty_tracker(), FlowLabels.fake(), TeamName.fake())
    assert created == FlowLabels.fake().labels


def test_seeding_again_leaves_the_group_as_it_was() -> None:
    tracker = empty_tracker()
    _ = seed_flow_labels(tracker, FlowLabels.fake(), TeamName.fake())
    _ = seed_flow_labels(tracker, FlowLabels.fake(), TeamName.fake())
    assert tracker.group_labels(FlowLabels.fake().group, TeamKey.fake()) == FlowLabels.fake().labels


def test_seeding_again_creates_nothing() -> None:
    tracker = empty_tracker()
    _ = seed_flow_labels(tracker, FlowLabels.fake(), TeamName.fake())
    assert seed_flow_labels(tracker, FlowLabels.fake(), TeamName.fake()) == LabelNames(())


def test_seeding_adds_only_the_labels_the_team_group_lacks() -> None:
    wanted = FlowLabels.fake()
    grilling = LabelNames((LabelName("Grilling"),))
    tracker = FakeTicketTracker(
        LabelNames(()), (), team_groups={(TeamKey.fake(), wanted.group): grilling}
    )
    _ = seed_flow_labels(tracker, wanted, TeamName.fake())
    assert tracker.group_labels(wanted.group, TeamKey.fake()) == wanted.labels


def workspace_seeded() -> FakeTicketTracker:
    wanted = FlowLabels.fake()
    return FakeTicketTracker(wanted.labels, (), groups={wanted.group: wanted.labels})


def test_a_workspace_flow_group_covers_the_team() -> None:
    covered = seed_flow_labels(workspace_seeded(), FlowLabels.fake(), TeamName.fake())
    assert covered == CoveredByWorkspace(group=FlowLabels.fake().group)


def test_a_workspace_flow_group_leaves_the_team_without_labels() -> None:
    tracker = workspace_seeded()
    _ = seed_flow_labels(tracker, FlowLabels.fake(), TeamName.fake())
    assert tracker.group_labels(FlowLabels.fake().group, TeamKey.fake()) == LabelNames(())


def test_an_unknown_team_fails_and_creates_nothing() -> None:
    tracker = empty_tracker()
    unknown = TeamName("Nowhere")
    with pytest.raises(TicketTrackerError, match=unknown.root):
        _ = seed_flow_labels(tracker, FlowLabels.fake(), unknown)
    assert tracker.group_labels(FlowLabels.fake().group, TeamKey.fake()) == LabelNames(())
