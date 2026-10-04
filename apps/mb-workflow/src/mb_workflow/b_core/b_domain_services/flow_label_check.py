from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from mb_workflow.b_core.d_domain_model.issue import ColoredLabels

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
        TicketTracker,
        TicketTrackerError,
    )
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier, TeamKey


class MissingFlowLabelsError(Exception):
    pass


class FlowLabelCheck:
    @staticmethod
    def held_labels(
        tracker: TicketTracker, wanted: FlowLabels, team: TeamKey | None
    ) -> Result[ColoredLabels, TicketTrackerError]:
        match tracker.group_labels(wanted.group, None):
            case Ok(workspace):
                if team is None:
                    return Ok(workspace)
                match tracker.group_labels(wanted.group, team):
                    case Ok(own):
                        return Ok(ColoredLabels((*own.root, *workspace.root)))
                    case Err() as failed:
                        return failed
            case Err() as failed:
                return failed

    @staticmethod
    def require(
        tracker: TicketTracker, wanted: FlowLabels, team: TeamKey | None
    ) -> Result[None, TicketTrackerError | MissingFlowLabelsError]:
        match FlowLabelCheck.held_labels(tracker, wanted, team):
            case Ok(held):
                missing = wanted.missing(held.label_names())
                if missing.root:
                    return Err(
                        MissingFlowLabelsError(
                            f"The {wanted.group.root} label group lacks"
                            f" {', '.join(label.root for label in missing.root)}."
                            " Run `mw flow seed-labels --team <team name>` to create them."
                        )
                    )
                return Ok(None)
            case Err() as failed:
                return failed

    @staticmethod
    def require_for_issue(
        tracker: TicketTracker, wanted: FlowLabels, issue: IssueIdentifier
    ) -> Result[None, TicketTrackerError | MissingFlowLabelsError]:
        match tracker.team_of(issue):
            case Ok(team):
                return FlowLabelCheck.require(tracker, wanted, team)
            case Err() as failed:
                return failed
