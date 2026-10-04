from safe_result import Err

from mb_workflow.b_core.a_features.seed_labels import (
    CoveredByWorkspace,
    FlowLabelSeeding,
    SeededTeam,
)
from mb_workflow.b_core.b_domain_services.flow_transition import Force
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
    FakeTicketTracker,
    TrackedIssue,
)
from mb_workflow.b_core.d_domain_model.flow_labels import (
    FlowLabels,
    GroupSync,
    LabelRename,
    LabelRenames,
)
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

    # The one ticket carries the label, so a test can see whether renaming or deleting reached it.
    @staticmethod
    def with_team_ticket_carrying(label: LabelName) -> FakeTicketTracker:
        return FakeTicketTracker(
            LabelNames(()),
            (SeedingTrackers.carrying(label),),
            team_groups={(TeamKey.fake(), FlowLabels.fake().group): LabelNames((label,))},
        )

    @staticmethod
    def with_workspace_ticket_carrying(label: LabelName) -> FakeTicketTracker:
        held = LabelNames((label,))
        return FakeTicketTracker(
            held,
            (SeedingTrackers.carrying(label),),
            groups={FlowLabels.fake().group: held},
        )

    @staticmethod
    def carrying(label: LabelName) -> TrackedIssue:
        tracked = TrackedIssue.fake()
        return tracked.model_copy(
            update={"issue": tracked.issue.model_copy(update={"labels": LabelNames((label,))})}
        )


def test_seeding_creates_every_flow_label_in_the_team() -> None:
    tracker = SeedingTrackers.empty()
    _ = FlowLabelSeeding.seed_flow_labels(
        tracker, FlowLabels.fake(), TeamName.fake(), Force(False)
    ).unwrap()
    held = tracker.group_labels(FlowLabels.fake().group, TeamKey.fake()).unwrap()
    assert held.label_names() == FlowLabels.fake().labels


def test_seeding_colors_entry_labels_yellow_and_the_rest_grey() -> None:
    tracker = SeedingTrackers.empty()
    _ = FlowLabelSeeding.seed_flow_labels(
        tracker, FlowLabels.fake(), TeamName.fake(), Force(False)
    ).unwrap()
    held = tracker.group_labels(FlowLabels.fake().group, TeamKey.fake()).unwrap()
    assert held == FlowLabels.fake().colored(FlowLabels.fake().labels)


def test_seeding_a_team_creates_no_workspace_labels() -> None:
    tracker = SeedingTrackers.empty()
    _ = FlowLabelSeeding.seed_flow_labels(
        tracker, FlowLabels.fake(), TeamName.fake(), Force(False)
    ).unwrap()
    assert tracker.group_labels(FlowLabels.fake().group, None).unwrap() == ColoredLabels(())


def test_seeding_a_team_leaves_other_teams_without_flow_labels() -> None:
    tracker = SeedingTrackers.empty()
    _ = FlowLabelSeeding.seed_flow_labels(
        tracker, FlowLabels.fake(), TeamName.fake(), Force(False)
    ).unwrap()
    other = SeedingTrackers.other_team().key
    assert tracker.group_labels(FlowLabels.fake().group, other).unwrap() == ColoredLabels(())


def test_seeding_reports_the_labels_it_created() -> None:
    seeded = FlowLabelSeeding.seed_flow_labels(
        SeedingTrackers.empty(), FlowLabels.fake(), TeamName.fake(), Force(False)
    ).unwrap()
    assert seeded == SeededTeam(
        created=FlowLabels.fake().labels,
        workspace=GroupSync.unchanged(),
        team=GroupSync.unchanged(),
    )


def test_seeding_again_creates_nothing() -> None:
    tracker = SeedingTrackers.empty()
    _ = FlowLabelSeeding.seed_flow_labels(
        tracker, FlowLabels.fake(), TeamName.fake(), Force(False)
    ).unwrap()
    seeded = FlowLabelSeeding.seed_flow_labels(
        tracker, FlowLabels.fake(), TeamName.fake(), Force(False)
    ).unwrap()
    assert seeded == SeededTeam(
        created=LabelNames(()), workspace=GroupSync.unchanged(), team=GroupSync.unchanged()
    )


def test_seeding_adds_only_the_labels_the_team_group_lacks() -> None:
    wanted = FlowLabels.fake()
    tracker = SeedingTrackers.empty()
    grilling = LabelNames((LabelName("Grilling"),))
    tracker.create_group_labels(wanted.group, wanted.colored(grilling), TeamKey.fake())
    _ = FlowLabelSeeding.seed_flow_labels(tracker, wanted, TeamName.fake(), Force(False)).unwrap()
    assert (
        tracker.group_labels(wanted.group, TeamKey.fake()).unwrap().label_names() == wanted.labels
    )


def test_seeding_recolors_team_labels_in_the_wrong_color() -> None:
    wanted = FlowLabels.fake()
    tracker = SeedingTrackers.empty()
    grey = ColoredLabels((ColoredLabel(name=LabelName("Grilling"), color=LabelColor.grey()),))
    tracker.create_group_labels(wanted.group, grey, TeamKey.fake())
    _ = FlowLabelSeeding.seed_flow_labels(tracker, wanted, TeamName.fake(), Force(False)).unwrap()
    held = tracker.group_labels(wanted.group, TeamKey.fake()).unwrap()
    assert wanted.miscolored(held) == LabelNames(())


def test_seeding_reports_the_labels_it_recolored() -> None:
    wanted = FlowLabels.fake()
    tracker = SeedingTrackers.empty()
    grilling = LabelName("Grilling")
    grey = ColoredLabels((ColoredLabel(name=grilling, color=LabelColor.grey()),))
    tracker.create_group_labels(wanted.group, grey, TeamKey.fake())
    seeded = FlowLabelSeeding.seed_flow_labels(
        tracker, wanted, TeamName.fake(), Force(False)
    ).unwrap()
    assert isinstance(seeded, SeededTeam)
    assert seeded.team.recolored == LabelNames((grilling,))


def test_seeding_recolors_workspace_labels_a_team_relies_on() -> None:
    wanted = FlowLabels.fake()
    tracker = SeedingTrackers.empty()
    qa = LabelName("QA")
    yellow = ColoredLabels((ColoredLabel(name=qa, color=LabelColor.yellow()),))
    tracker.create_group_labels(wanted.group, yellow, None)
    _ = FlowLabelSeeding.seed_flow_labels(tracker, wanted, TeamName.fake(), Force(False)).unwrap()
    assert wanted.miscolored(tracker.group_labels(wanted.group, None).unwrap()) == LabelNames(())


def test_a_complete_workspace_flow_group_covers_the_team() -> None:
    tracker = SeedingTrackers.with_workspace_group(FlowLabels.fake().labels)
    covered = FlowLabelSeeding.seed_flow_labels(
        tracker, FlowLabels.fake(), TeamName.fake(), Force(False)
    ).unwrap()
    assert isinstance(covered, CoveredByWorkspace)


def test_a_complete_workspace_flow_group_leaves_the_team_without_labels() -> None:
    tracker = SeedingTrackers.with_workspace_group(FlowLabels.fake().labels)
    _ = FlowLabelSeeding.seed_flow_labels(
        tracker, FlowLabels.fake(), TeamName.fake(), Force(False)
    ).unwrap()
    assert tracker.group_labels(FlowLabels.fake().group, TeamKey.fake()).unwrap() == ColoredLabels(
        ()
    )


def test_forced_seeding_creates_every_flow_label_in_the_team_beside_a_complete_workspace_group() -> (
    None
):
    wanted = FlowLabels.fake()
    tracker = SeedingTrackers.with_workspace_group(wanted.labels)
    seeded = FlowLabelSeeding.seed_flow_labels(
        tracker, wanted, TeamName.fake(), Force(True)
    ).unwrap()
    assert isinstance(seeded, SeededTeam)
    assert seeded.created == wanted.labels
    held = tracker.group_labels(wanted.group, TeamKey.fake()).unwrap()
    assert held.label_names() == wanted.labels


def test_forced_seeding_creates_in_the_team_the_labels_the_workspace_group_already_has() -> None:
    wanted = FlowLabels.fake()
    tracker = SeedingTrackers.with_workspace_group(LabelNames(wanted.labels.root[1:]))
    _ = FlowLabelSeeding.seed_flow_labels(tracker, wanted, TeamName.fake(), Force(True)).unwrap()
    held = tracker.group_labels(wanted.group, TeamKey.fake()).unwrap()
    assert held.label_names() == wanted.labels


def test_a_covering_workspace_group_recolors_and_reports_its_labels_in_the_wrong_color() -> None:
    wanted = FlowLabels.fake()
    tracker = SeedingTrackers.empty()
    qa = LabelName("QA")
    rest = LabelNames(tuple(label for label in wanted.labels.root if label != qa))
    tracker.create_group_labels(wanted.group, wanted.colored(rest), None)
    yellow = ColoredLabels((ColoredLabel(name=qa, color=LabelColor.yellow()),))
    tracker.create_group_labels(wanted.group, yellow, None)
    covered = FlowLabelSeeding.seed_flow_labels(
        tracker, wanted, TeamName.fake(), Force(False)
    ).unwrap()
    assert isinstance(covered, CoveredByWorkspace)
    assert covered.workspace.recolored == LabelNames((qa,))
    assert wanted.miscolored(tracker.group_labels(wanted.group, None).unwrap()) == LabelNames(())


def test_an_incomplete_workspace_flow_group_gets_the_rest_in_the_team() -> None:
    wanted = FlowLabels.fake()
    in_workspace = LabelNames(wanted.labels.root[1:])
    tracker = SeedingTrackers.with_workspace_group(in_workspace)
    seeded = FlowLabelSeeding.seed_flow_labels(
        tracker, wanted, TeamName.fake(), Force(False)
    ).unwrap()
    lacking = LabelNames(wanted.labels.root[:1])
    assert isinstance(seeded, SeededTeam)
    assert seeded.created == lacking
    assert tracker.group_labels(wanted.group, TeamKey.fake()).unwrap().label_names() == lacking


def test_an_unknown_team_fails_and_creates_nothing() -> None:
    tracker = SeedingTrackers.empty()
    unknown = TeamName("Nowhere")
    refused = FlowLabelSeeding.seed_flow_labels(tracker, FlowLabels.fake(), unknown, Force(False))
    assert isinstance(refused, Err)
    assert unknown.root in str(refused.error)
    assert tracker.group_labels(FlowLabels.fake().group, TeamKey.fake()).unwrap() == ColoredLabels(
        ()
    )


def test_unforced_seeding_with_a_pending_rename_changes_nothing() -> None:
    held = LabelName(FlowLabels.fake().labels.root[0].root.casefold())
    tracker = SeedingTrackers.with_team_ticket_carrying(held)
    refused = FlowLabelSeeding.seed_flow_labels(
        tracker, FlowLabels.fake(), TeamName.fake(), Force(False)
    )
    assert isinstance(refused, Err)
    group = tracker.group_labels(FlowLabels.fake().group, TeamKey.fake()).unwrap()
    assert group.label_names() == LabelNames((held,))


def test_unforced_seeding_with_a_pending_deletion_changes_nothing() -> None:
    obsolete = LabelName("Obsolete")
    tracker = SeedingTrackers.with_team_ticket_carrying(obsolete)
    _ = FlowLabelSeeding.seed_flow_labels(tracker, FlowLabels.fake(), TeamName.fake(), Force(False))
    issue = tracker.read_issue(TrackedIssue.fake().issue.identifier).unwrap()
    assert issue.labels == LabelNames((obsolete,))


def test_the_refusal_lists_each_pending_rename_with_its_ticket_count() -> None:
    renamed = FlowLabels.fake().labels.root[0]
    held = LabelName(renamed.root.casefold())
    one_ticket = "on 1 ticket"
    rerun = "--force"
    refused = FlowLabelSeeding.seed_flow_labels(
        SeedingTrackers.with_team_ticket_carrying(held),
        FlowLabels.fake(),
        TeamName.fake(),
        Force(False),
    )
    assert isinstance(refused, Err)
    assert f"Rename {held.root} to {renamed.root}" in str(refused.error)
    assert one_ticket in str(refused.error)
    assert rerun in str(refused.error)


def test_the_refusal_lists_each_pending_deletion_with_its_ticket_count() -> None:
    obsolete = LabelName("Obsolete")
    one_ticket = "on 1 ticket"
    refused = FlowLabelSeeding.seed_flow_labels(
        SeedingTrackers.with_workspace_ticket_carrying(obsolete),
        FlowLabels.fake(),
        TeamName.fake(),
        Force(False),
    )
    assert isinstance(refused, Err)
    assert f"Delete {obsolete.root}" in str(refused.error)
    assert one_ticket in str(refused.error)


def test_forced_seeding_renames_a_team_label_spelled_in_another_case() -> None:
    wanted = FlowLabels.fake()
    held = LabelName(wanted.labels.root[0].root.casefold())
    tracker = SeedingTrackers.with_team_ticket_carrying(held)
    _ = FlowLabelSeeding.seed_flow_labels(tracker, wanted, TeamName.fake(), Force(True)).unwrap()
    group = tracker.group_labels(wanted.group, TeamKey.fake()).unwrap()
    assert set(group.label_names().root) == set(wanted.labels.root)


def test_forced_seeding_keeps_a_renamed_label_on_its_tickets() -> None:
    renamed = FlowLabels.fake().labels.root[0]
    tracker = SeedingTrackers.with_team_ticket_carrying(LabelName(renamed.root.casefold()))
    _ = FlowLabelSeeding.seed_flow_labels(
        tracker, FlowLabels.fake(), TeamName.fake(), Force(True)
    ).unwrap()
    issue = tracker.read_issue(TrackedIssue.fake().issue.identifier).unwrap()
    assert issue.labels == LabelNames((renamed,))


def test_forced_seeding_deletes_a_team_label_outside_the_spec_from_the_group_and_tickets() -> None:
    wanted = FlowLabels.fake()
    tracker = SeedingTrackers.with_team_ticket_carrying(LabelName("Obsolete"))
    _ = FlowLabelSeeding.seed_flow_labels(tracker, wanted, TeamName.fake(), Force(True)).unwrap()
    group = tracker.group_labels(wanted.group, TeamKey.fake()).unwrap()
    assert group.label_names() == wanted.labels
    issue = tracker.read_issue(TrackedIssue.fake().issue.identifier).unwrap()
    assert issue.labels == LabelNames(())


def test_forced_seeding_renames_and_deletes_in_the_workspace_group() -> None:
    wanted = FlowLabels.fake()
    tracker = SeedingTrackers.with_workspace_group(
        LabelNames(
            (
                *wanted.labels.root[1:],
                LabelName(wanted.labels.root[0].root.casefold()),
                LabelName("Obsolete"),
            )
        )
    )
    _ = FlowLabelSeeding.seed_flow_labels(tracker, wanted, TeamName.fake(), Force(True)).unwrap()
    group = tracker.group_labels(wanted.group, None).unwrap()
    assert set(group.label_names().root) == set(wanted.labels.root)


def test_forced_seeding_reports_its_renames_and_deletions() -> None:
    wanted = FlowLabels.fake()
    held = LabelName(wanted.labels.root[0].root.casefold())
    obsolete = LabelName("Obsolete")
    tracker = SeedingTrackers.with_workspace_group(
        LabelNames((*wanted.labels.root[1:], held, obsolete))
    )
    covered = FlowLabelSeeding.seed_flow_labels(
        tracker, wanted, TeamName.fake(), Force(True)
    ).unwrap()
    assert covered.workspace.renamed == LabelRenames(
        (LabelRename(held=held, renamed=wanted.labels.root[0]),)
    )
    assert covered.workspace.deleted == LabelNames((obsolete,))
