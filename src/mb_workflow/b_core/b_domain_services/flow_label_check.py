from typing import TYPE_CHECKING

from mb_workflow.b_core.d_domain_model.issue import ColoredLabels

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.issue import TeamKey


class MissingFlowLabelsError(Exception):
    pass


class FlowLabelCheck:
    # A team's own flow labels come first, and the workspace's fill in any it lacks.
    @staticmethod
    def held_labels(
        tracker: TicketTracker, wanted: FlowLabels, team: TeamKey | None
    ) -> ColoredLabels:
        workspace = tracker.group_labels(wanted.group, None)
        if team is None:
            return workspace
        return ColoredLabels((*tracker.group_labels(wanted.group, team).root, *workspace.root))

    @staticmethod
    def require(tracker: TicketTracker, wanted: FlowLabels, team: TeamKey | None) -> None:
        held = FlowLabelCheck.held_labels(tracker, wanted, team)
        missing = wanted.missing(held.label_names())
        if missing.root:
            raise MissingFlowLabelsError(
                f"The {wanted.group.root} label group lacks"
                f" {', '.join(label.root for label in missing.root)}."
                " Run `mw flow seed-labels --team <team name>` to create them."
            )
