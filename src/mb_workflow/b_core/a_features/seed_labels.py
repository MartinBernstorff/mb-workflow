from typing import TYPE_CHECKING

from mb_workflow.b_core.d_domain_model.issue import LabelGroupName
from mb_workflow.d_lib.models import Model

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.issue import LabelNames, TeamName


class CoveredByWorkspace(Model):
    group: LabelGroupName

    @staticmethod
    def fake() -> CoveredByWorkspace:
        return CoveredByWorkspace(group=LabelGroupName.fake())


# A workspace-level group already serves every team, so seeding a team beside it would only shadow it.
def seed_flow_labels(
    tracker: TicketTracker, wanted: FlowLabels, team: TeamName
) -> LabelNames | CoveredByWorkspace:
    key = tracker.team_named(team)
    if tracker.group_labels(wanted.group, None).root:
        return CoveredByWorkspace(group=wanted.group)
    missing = wanted.missing(tracker.group_labels(wanted.group, key))
    if missing.root:
        tracker.create_group_labels(wanted.group, missing, key)
    return missing
