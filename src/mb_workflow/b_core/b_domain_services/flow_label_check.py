from typing import TYPE_CHECKING

from mb_workflow.b_core.d_domain_model.issue import LabelNames

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.issue import TeamKey


class MissingFlowLabelsError(Exception):
    pass


# A team's own flow labels come first, and the workspace's fill in any it lacks.
def held_flow_labels(
    tracker: TicketTracker, wanted: FlowLabels, team: TeamKey | None
) -> LabelNames:
    workspace = tracker.group_labels(wanted.group, None)
    if team is None:
        return workspace
    return LabelNames((*tracker.group_labels(wanted.group, team).root, *workspace.root))


def require_flow_labels(tracker: TicketTracker, wanted: FlowLabels, team: TeamKey | None) -> None:
    missing = wanted.missing(held_flow_labels(tracker, wanted, team))
    if missing.root:
        raise MissingFlowLabelsError(
            f"The {wanted.group.root} label group lacks"
            f" {', '.join(label.root for label in missing.root)}."
            " Run `mw flow seed-labels --team <team name>` to create them."
        )
