import pytest

from mb_workflow.b_core.a_features.seed_labels import (
    CoveredByWorkspace,
    SeededTeam,
    seed_flow_labels,
)
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
    FakeTicketTracker,
    TicketTrackerError,
)
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
from mb_workflow.b_core.d_domain_model.issue import (
    ColoredLabel,
    ColoredLabels,
    LabelColor,
    LabelName,
    LabelNames,
    Team,
    TeamKey,
    TeamName,
)


class SeedingTrackers:
    @staticmethod
    def other_team() -> Team:
        return Team(key=TeamKey("OPS"), name=TeamName("Operations"), projects=())

    @staticmethod
    def empty() -> FakeTicketTracker:
        return FakeTicketTracker(
            LabelNames(()), (), teams=(Team.fake(), SeedingTrackers.other_team())
        )

    @staticmethod
    def with_workspace_group(labels: LabelNames) -> FakeTicketTracker:
        return FakeTicketTracker(labels, (), groups={FlowLabels.fake().group: labels})


def test_seeding_creates_every_flow_label_in_the_team() -> None:
    tracker = SeedingTrackers.empty()
    _ = seed_flow_labels(tracker, FlowLabels.fake(), TeamName.fake())
    held = tracker.group_labels(FlowLabels.fake().group, TeamKey.fake())
    assert held.label_names() == FlowLabels.fake().labels


def test_seeding_colors_entry_labels_yellow_and_the_rest_grey() -> None:
    tracker = SeedingTrackers.empty()
    _ = seed_flow_labels(tracker, FlowLabels.fake(), TeamName.fake())
    held = tracker.group_labels(FlowLabels.fake().group, TeamKey.fake())
    assert held == FlowLabels.fake().colored(FlowLabels.fake().labels)


def test_seeding_a_team_creates_no_workspace_labels() -> None:
    tracker = SeedingTrackers.empty()
    _ = seed_flow_labels(tracker, FlowLabels.fake(), TeamName.fake())
    assert tracker.group_labels(FlowLabels.fake().group, None) == ColoredLabels(())


def test_seeding_a_team_leaves_other_teams_without_flow_labels() -> None:
    tracker = SeedingTrackers.empty()
    _ = seed_flow_labels(tracker, FlowLabels.fake(), TeamName.fake())
    other = SeedingTrackers.other_team().key
    assert tracker.group_labels(FlowLabels.fake().group, other) == ColoredLabels(())


def test_seeding_reports_the_labels_it_created() -> None:
    seeded = seed_flow_labels(SeedingTrackers.empty(), FlowLabels.fake(), TeamName.fake())
    assert seeded == SeededTeam(created=FlowLabels.fake().labels, recolored=LabelNames(()))


def test_seeding_again_creates_nothing() -> None:
    tracker = SeedingTrackers.empty()
    _ = seed_flow_labels(tracker, FlowLabels.fake(), TeamName.fake())
    seeded = seed_flow_labels(tracker, FlowLabels.fake(), TeamName.fake())
    assert seeded == SeededTeam(created=LabelNames(()), recolored=LabelNames(()))


def test_seeding_adds_only_the_labels_the_team_group_lacks() -> None:
    wanted = FlowLabels.fake()
    tracker = SeedingTrackers.empty()
    grilling = LabelNames((LabelName("Grilling"),))
    tracker.create_group_labels(wanted.group, wanted.colored(grilling), TeamKey.fake())
    _ = seed_flow_labels(tracker, wanted, TeamName.fake())
    assert tracker.group_labels(wanted.group, TeamKey.fake()).label_names() == wanted.labels


def test_seeding_recolors_team_labels_in_the_wrong_color() -> None:
    wanted = FlowLabels.fake()
    tracker = SeedingTrackers.empty()
    grey = ColoredLabels((ColoredLabel(name=LabelName("Grilling"), color=LabelColor.grey()),))
    tracker.create_group_labels(wanted.group, grey, TeamKey.fake())
    _ = seed_flow_labels(tracker, wanted, TeamName.fake())
    held = tracker.group_labels(wanted.group, TeamKey.fake())
    assert wanted.miscolored(held) == LabelNames(())


def test_seeding_reports_the_labels_it_recolored() -> None:
    wanted = FlowLabels.fake()
    tracker = SeedingTrackers.empty()
    grilling = LabelName("Grilling")
    grey = ColoredLabels((ColoredLabel(name=grilling, color=LabelColor.grey()),))
    tracker.create_group_labels(wanted.group, grey, TeamKey.fake())
    seeded = seed_flow_labels(tracker, wanted, TeamName.fake())
    assert isinstance(seeded, SeededTeam)
    assert seeded.recolored == LabelNames((grilling,))


def test_seeding_recolors_workspace_labels_a_team_relies_on() -> None:
    wanted = FlowLabels.fake()
    tracker = SeedingTrackers.empty()
    qa = LabelName("QA")
    yellow = ColoredLabels((ColoredLabel(name=qa, color=LabelColor.yellow()),))
    tracker.create_group_labels(wanted.group, yellow, None)
    _ = seed_flow_labels(tracker, wanted, TeamName.fake())
    assert wanted.miscolored(tracker.group_labels(wanted.group, None)) == LabelNames(())


def test_a_complete_workspace_flow_group_covers_the_team() -> None:
    tracker = SeedingTrackers.with_workspace_group(FlowLabels.fake().labels)
    covered = seed_flow_labels(tracker, FlowLabels.fake(), TeamName.fake())
    assert isinstance(covered, CoveredByWorkspace)


def test_a_complete_workspace_flow_group_leaves_the_team_without_labels() -> None:
    tracker = SeedingTrackers.with_workspace_group(FlowLabels.fake().labels)
    _ = seed_flow_labels(tracker, FlowLabels.fake(), TeamName.fake())
    assert tracker.group_labels(FlowLabels.fake().group, TeamKey.fake()) == ColoredLabels(())


def test_a_covering_workspace_group_recolors_and_reports_its_labels_in_the_wrong_color() -> None:
    wanted = FlowLabels.fake()
    tracker = SeedingTrackers.empty()
    qa = LabelName("QA")
    rest = LabelNames(tuple(label for label in wanted.labels.root if label != qa))
    tracker.create_group_labels(wanted.group, wanted.colored(rest), None)
    yellow = ColoredLabels((ColoredLabel(name=qa, color=LabelColor.yellow()),))
    tracker.create_group_labels(wanted.group, yellow, None)
    covered = seed_flow_labels(tracker, wanted, TeamName.fake())
    assert covered == CoveredByWorkspace(group=wanted.group, recolored=LabelNames((qa,)))
    assert wanted.miscolored(tracker.group_labels(wanted.group, None)) == LabelNames(())


def test_an_incomplete_workspace_flow_group_gets_the_rest_in_the_team() -> None:
    wanted = FlowLabels.fake()
    in_workspace = LabelNames(wanted.labels.root[1:])
    tracker = SeedingTrackers.with_workspace_group(in_workspace)
    seeded = seed_flow_labels(tracker, wanted, TeamName.fake())
    lacking = LabelNames(wanted.labels.root[:1])
    assert isinstance(seeded, SeededTeam)
    assert seeded.created == lacking
    assert tracker.group_labels(wanted.group, TeamKey.fake()).label_names() == lacking


def test_an_unknown_team_fails_and_creates_nothing() -> None:
    tracker = SeedingTrackers.empty()
    unknown = TeamName("Nowhere")
    with pytest.raises(TicketTrackerError, match=unknown.root):
        _ = seed_flow_labels(tracker, FlowLabels.fake(), unknown)
    assert tracker.group_labels(FlowLabels.fake().group, TeamKey.fake()) == ColoredLabels(())
