from typing import TYPE_CHECKING

from mb_workflow.b_core.b_domain_services.flow_label_check import FlowLabelCheck
from mb_workflow.b_core.d_domain_model.issue import LabelGroupName, LabelNames
from mb_workflow.d_lib.models import Model

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.issue import TeamName


class CoveredByWorkspace(Model):
    group: LabelGroupName
    miscolored: LabelNames

    @staticmethod
    def fake() -> CoveredByWorkspace:
        return CoveredByWorkspace(group=LabelGroupName.fake(), miscolored=LabelNames(()))


class SeededTeam(Model):
    created: LabelNames
    miscolored: LabelNames

    @staticmethod
    def fake() -> SeededTeam:
        return SeededTeam(created=LabelNames.fake(), miscolored=LabelNames(()))


# A complete workspace-level group already serves every team, so seeding a team beside it would only shadow it.
def seed_flow_labels(
    tracker: TicketTracker, wanted: FlowLabels, team: TeamName
) -> CoveredByWorkspace | SeededTeam:
    key = tracker.team_named(team)
    workspace = tracker.group_labels(wanted.group, None)
    if not wanted.missing(workspace.label_names()).root:
        return CoveredByWorkspace(group=wanted.group, miscolored=wanted.miscolored(workspace))
    held = FlowLabelCheck.held_labels(tracker, wanted, key)
    missing = wanted.missing(held.label_names())
    if missing.root:
        tracker.create_group_labels(wanted.group, wanted.colored(missing), key)
    return SeededTeam(created=missing, miscolored=wanted.miscolored(held))
