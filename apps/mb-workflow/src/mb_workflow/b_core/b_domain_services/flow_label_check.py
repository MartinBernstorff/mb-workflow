from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from mb_workflow.b_core.d_domain_model.issue import ColoredLabels, LabelName

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
        TicketTracker,
        TicketTrackerError,
    )
    from mb_workflow.b_core.d_domain_model.flow import StateName
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier, TeamKey


class MissingFlowLabelsError(Exception):
    pass


class FlowLabelCheck:
    # A team's own flow labels come first, and the workspace's fill in any it lacks.
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

    # Only the label of the state being entered is required, so a team may go without the labels of states it never uses.
    @staticmethod
    def require(
        tracker: TicketTracker, wanted: FlowLabels, team: TeamKey | None, state: StateName
    ) -> Result[None, TicketTrackerError | MissingFlowLabelsError]:
        match FlowLabelCheck.held_labels(tracker, wanted, team):
            case Ok(held):
                missing = wanted.missing(held.label_names()).matching(LabelName(state.root))
                if missing is not None:
                    return Err(
                        MissingFlowLabelsError(
                            f"The {wanted.group.root} label group lacks {missing.root}."
                            " Run `mw flow seed-labels --team <team name>` to create them."
                        )
                    )
                return Ok(None)
            case Err() as failed:
                return failed

    # Checks the flow labels the issue's own team can use.
    @staticmethod
    def require_for_issue(
        tracker: TicketTracker, wanted: FlowLabels, issue: IssueIdentifier, state: StateName
    ) -> Result[None, TicketTrackerError | MissingFlowLabelsError]:
        match tracker.team_of(issue):
            case Ok(team):
                return FlowLabelCheck.require(tracker, wanted, team, state)
            case Err() as failed:
                return failed
