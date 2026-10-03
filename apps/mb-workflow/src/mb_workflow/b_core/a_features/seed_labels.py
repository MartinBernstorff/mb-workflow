from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from mb_workflow.b_core.d_domain_model.issue import LabelGroupName, LabelNames
from mb_workflow.d_lib.models import Model

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
        TicketTracker,
        TicketTrackerError,
    )
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.issue import ColoredLabels, TeamKey, TeamName


class CoveredByWorkspace(Model):
    group: LabelGroupName
    recolored: LabelNames

    @staticmethod
    def fake() -> CoveredByWorkspace:
        return CoveredByWorkspace(group=LabelGroupName.fake(), recolored=LabelNames(()))


class SeededTeam(Model):
    created: LabelNames
    recolored: LabelNames

    @staticmethod
    def fake() -> SeededTeam:
        return SeededTeam(created=LabelNames.fake(), recolored=LabelNames(()))


class FlowLabelSeeding:
    # A complete workspace-level group already serves every team, so seeding a team beside it would only shadow it.
    @staticmethod
    def seed_flow_labels(
        tracker: TicketTracker, wanted: FlowLabels, team: TeamName
    ) -> Result[CoveredByWorkspace | SeededTeam, TicketTrackerError]:
        key = tracker.team_named(team)
        if isinstance(key, Err):
            return key
        workspace = tracker.group_labels(wanted.group, None)
        if isinstance(workspace, Err):
            return workspace
        if not wanted.missing(workspace.value.label_names()).root:
            recolored = FlowLabelSeeding.recolor(tracker, wanted, workspace.value, None)
            return Ok(CoveredByWorkspace(group=wanted.group, recolored=recolored))
        held = tracker.group_labels(wanted.group, key.value)
        if isinstance(held, Err):
            return held
        missing = wanted.missing(
            LabelNames((*held.value.label_names().root, *workspace.value.label_names().root))
        )
        if missing.root:
            tracker.create_group_labels(wanted.group, wanted.colored(missing), key.value)
        recolored = (
            *FlowLabelSeeding.recolor(tracker, wanted, held.value, key.value).root,
            *FlowLabelSeeding.recolor(tracker, wanted, workspace.value, None).root,
        )
        return Ok(SeededTeam(created=missing, recolored=LabelNames(recolored)))

    @staticmethod
    def recolor(
        tracker: TicketTracker, wanted: FlowLabels, held: ColoredLabels, team: TeamKey | None
    ) -> LabelNames:
        miscolored = wanted.miscolored(held)
        if miscolored.root:
            tracker.recolor_group_labels(wanted.group, wanted.colored(miscolored), team)
        return miscolored
