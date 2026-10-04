import logging
from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from mb_workflow.b_core.d_domain_model.flow_labels import GroupSync
from mb_workflow.b_core.d_domain_model.issue import LabelGroupName, LabelNames, TeamKey
from mb_workflow.d_lib.logging import Activity
from mb_workflow.d_lib.models import Model, Value

if TYPE_CHECKING:
    from mb_workflow.b_core.b_domain_services.flow_transition import Force
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
        TicketTracker,
        TicketTrackerError,
    )
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.issue import (
        ColoredLabels,
        TeamName,
    )


logger = logging.getLogger(__name__)


class PendingLabelChangesError(Exception):
    pass


class CoveredByWorkspace(Model):
    group: LabelGroupName
    workspace: GroupSync
    team: GroupSync

    @staticmethod
    def fake() -> CoveredByWorkspace:
        return CoveredByWorkspace(
            group=LabelGroupName.fake(), workspace=GroupSync.fake(), team=GroupSync.fake()
        )


class SeededTeam(Model):
    created: LabelNames
    workspace: GroupSync
    team: GroupSync

    @staticmethod
    def fake() -> SeededTeam:
        return SeededTeam(
            created=LabelNames.fake(), workspace=GroupSync.fake(), team=GroupSync.fake()
        )


# A team of None is the workspace-level group.
class PlannedGroup(Model):
    team: TeamKey | None
    sync: GroupSync

    @staticmethod
    def fake() -> PlannedGroup:
        return PlannedGroup(team=TeamKey.fake(), sync=GroupSync.fake())

    def place(self, group: LabelGroupName) -> GroupPlace:
        return GroupPlace.of(group, self.team)


# Where a label group lives, worded for a log line or an error.
class GroupPlace(Value[str]):
    @staticmethod
    def fake() -> GroupPlace:
        return GroupPlace("the workspace's flowy group")

    @staticmethod
    def of(group: LabelGroupName, team: TeamKey | None) -> GroupPlace:
        if team is None:
            return GroupPlace(f"the workspace's {group.root} group")
        return GroupPlace(f"the {group.root} group of team {team.root}")


class FlowLabelSeeding:
    # A complete workspace-level group already serves every team, so seeding a team beside it would only shadow it.
    # --force seeds the team anyway, for a team that should keep its own labels.
    @staticmethod
    def seed_flow_labels(
        tracker: TicketTracker, wanted: FlowLabels, team: TeamName, force: Force
    ) -> Result[CoveredByWorkspace | SeededTeam, TicketTrackerError | PendingLabelChangesError]:
        with Activity(f"Looking up team {team.root}").logged(logger):
            key = tracker.team_named(team)
        if isinstance(key, Err):
            return key
        groups = FlowLabelSeeding.read_groups(tracker, wanted.group, key.value)
        if isinstance(groups, Err):
            return groups
        workspace, held = groups.value
        workspace_sync = wanted.sync_plan(workspace)
        team_sync = wanted.sync_plan(held)
        synced = FlowLabelSeeding.sync_groups(
            tracker,
            wanted,
            (
                PlannedGroup(team=None, sync=workspace_sync),
                PlannedGroup(team=key.value, sync=team_sync),
            ),
            force,
        )
        if isinstance(synced, Err):
            return synced
        if not force.root and not wanted.missing(workspace.label_names()).root:
            return Ok(
                CoveredByWorkspace(group=wanted.group, workspace=workspace_sync, team=team_sync)
            )
        missing = (
            wanted.missing(held.label_names())
            if force.root
            else FlowLabelSeeding.missing_labels(wanted, workspace, held)
        )
        if missing.root:
            with Activity(
                f"Creating {', '.join(label.root for label in missing.root)}"
                f" in {GroupPlace.of(wanted.group, key.value).root}"
            ).logged(logger):
                created = tracker.create_group_labels(
                    wanted.group, wanted.colored(missing), key.value
                )
            if isinstance(created, Err):
                return created
        return Ok(SeededTeam(created=missing, workspace=workspace_sync, team=team_sync))

    # The group at workspace level, then the team's own.
    @staticmethod
    def read_groups(
        tracker: TicketTracker, group: LabelGroupName, team: TeamKey
    ) -> Result[tuple[ColoredLabels, ColoredLabels], TicketTrackerError]:
        with Activity(f"Reading {GroupPlace.of(group, None).root}").logged(logger):
            workspace = tracker.group_labels(group, None)
        if isinstance(workspace, Err):
            return workspace
        with Activity(f"Reading {GroupPlace.of(group, team).root}").logged(logger):
            held = tracker.group_labels(group, team)
        if isinstance(held, Err):
            return held
        return Ok((workspace.value, held.value))

    @staticmethod
    def missing_labels(
        wanted: FlowLabels, workspace: ColoredLabels, held: ColoredLabels
    ) -> LabelNames:
        return wanted.missing(LabelNames((*held.label_names().root, *workspace.label_names().root)))

    @staticmethod
    def sync_groups(
        tracker: TicketTracker, wanted: FlowLabels, plans: tuple[PlannedGroup, ...], force: Force
    ) -> Result[None, TicketTrackerError | PendingLabelChangesError]:
        if not force.root:
            checked = FlowLabelSeeding.refuse_unforced_changes(tracker, wanted.group, plans)
            if isinstance(checked, Err):
                return checked
        for plan in plans:
            applied = FlowLabelSeeding.apply_sync(tracker, wanted, plan)
            if isinstance(applied, Err):
                return applied
        return Ok(None)

    # Renaming or deleting a label changes every ticket that carries it, so it waits for --force.
    @staticmethod
    def refuse_unforced_changes(
        tracker: TicketTracker, group: LabelGroupName, plans: tuple[PlannedGroup, ...]
    ) -> Result[None, TicketTrackerError | PendingLabelChangesError]:
        pending: list[str] = []
        for plan in plans:
            place = plan.place(group).root
            changes = (
                *(
                    (rename.held, f"Rename {rename.held.root} to {rename.renamed.root} in {place}")
                    for rename in plan.sync.renamed.root
                ),
                *((label, f"Delete {label.root} from {place}") for label in plan.sync.deleted.root),
            )
            for label, change in changes:
                with Activity(f"Counting the tickets that carry {label.root}").logged(logger):
                    counted = tracker.labelled_ticket_count(group, label, plan.team)
                if isinstance(counted, Err):
                    return counted
                tickets = counted.value.root
                pending.append(f"{change} (on {tickets} ticket{'' if tickets == 1 else 's'})")
        if not pending:
            return Ok(None)
        listed = "\n".join(f"  {change}" for change in pending)
        return Err(
            PendingLabelChangesError(
                f"Seeding would change the tickets that carry these labels:\n{listed}\n"
                "Rerun with --force to make the changes."
            )
        )

    @staticmethod
    def apply_sync(
        tracker: TicketTracker, wanted: FlowLabels, plan: PlannedGroup
    ) -> Result[None, TicketTrackerError]:
        place = plan.place(wanted.group).root
        for rename in plan.sync.renamed.root:
            with Activity(
                f"Renaming {rename.held.root} to {rename.renamed.root} in {place}"
            ).logged(logger):
                renamed = tracker.rename_group_label(
                    wanted.group, rename.held, rename.renamed, plan.team
                )
            if isinstance(renamed, Err):
                return renamed
        for label in plan.sync.deleted.root:
            with Activity(f"Deleting {label.root} from {place}").logged(logger):
                deleted = tracker.delete_group_label(wanted.group, label, plan.team)
            if isinstance(deleted, Err):
                return deleted
        if plan.sync.recolored.root:
            with Activity(
                f"Recoloring {', '.join(label.root for label in plan.sync.recolored.root)}"
                f" in {place}"
            ).logged(logger):
                return tracker.recolor_group_labels(
                    wanted.group, wanted.colored(plan.sync.recolored), plan.team
                )
        return Ok(None)
