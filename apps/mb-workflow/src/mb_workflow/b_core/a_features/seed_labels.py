from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from mb_workflow.b_core.d_domain_model.flow_labels import GroupSync
from mb_workflow.b_core.d_domain_model.issue import LabelGroupName, LabelNames, TeamKey
from mb_workflow.d_lib.models import Model

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


class FlowLabelSeeding:
    # A complete workspace-level group already serves every team, so seeding a team beside it would only shadow it.
    @staticmethod
    def seed_flow_labels(
        tracker: TicketTracker, wanted: FlowLabels, team: TeamName, force: Force
    ) -> Result[CoveredByWorkspace | SeededTeam, TicketTrackerError | PendingLabelChangesError]:
        key = tracker.team_named(team)
        if isinstance(key, Err):
            return key
        workspace = tracker.group_labels(wanted.group, None)
        if isinstance(workspace, Err):
            return workspace
        held = tracker.group_labels(wanted.group, key.value)
        if isinstance(held, Err):
            return held
        workspace_sync = wanted.sync_plan(workspace.value)
        team_sync = wanted.sync_plan(held.value)
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
        if not wanted.missing(workspace.value.label_names()).root:
            return Ok(
                CoveredByWorkspace(group=wanted.group, workspace=workspace_sync, team=team_sync)
            )
        missing = FlowLabelSeeding.missing_labels(wanted, workspace.value, held.value)
        if missing.root:
            tracker.create_group_labels(wanted.group, wanted.colored(missing), key.value)
        return Ok(SeededTeam(created=missing, workspace=workspace_sync, team=team_sync))

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
            place = (
                f"the workspace's {group.root} group"
                if plan.team is None
                else f"the {group.root} group of team {plan.team.root}"
            )
            changes = (
                *(
                    (rename.held, f"Rename {rename.held.root} to {rename.renamed.root} in {place}")
                    for rename in plan.sync.renamed.root
                ),
                *((label, f"Delete {label.root} from {place}") for label in plan.sync.deleted.root),
            )
            for label, change in changes:
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
        for rename in plan.sync.renamed.root:
            renamed = tracker.rename_group_label(
                wanted.group, rename.held, rename.renamed, plan.team
            )
            if isinstance(renamed, Err):
                return renamed
        for label in plan.sync.deleted.root:
            deleted = tracker.delete_group_label(wanted.group, label, plan.team)
            if isinstance(deleted, Err):
                return deleted
        if plan.sync.recolored.root:
            tracker.recolor_group_labels(
                wanted.group, wanted.colored(plan.sync.recolored), plan.team
            )
        return Ok(None)
