import re

from safe_result import Err, Ok

from mb_workflow.b_core.b_domain_services.flow_label_check import (
    FlowLabelCheck,
    MissingFlowLabelsError,
)
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import FakeTicketTracker
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
from mb_workflow.b_core.d_domain_model.issue import LabelName, LabelNames, TeamKey


def test_a_workspace_holding_every_flow_label_passes() -> None:
    wanted = FlowLabels.fake()
    tracker = FakeTicketTracker(wanted.labels, (), groups={wanted.group: wanted.labels})
    assert FlowLabelCheck.require(tracker, wanted, None) == Ok(None)


def test_a_missing_flow_label_fails_and_points_to_seed_labels() -> None:
    wanted = FlowLabels.fake()
    held = LabelNames(wanted.labels.root[1:])
    tracker = FakeTicketTracker(held, (), groups={wanted.group: held})
    refused = FlowLabelCheck.require(tracker, wanted, None)
    assert isinstance(refused, Err)
    assert isinstance(refused.error, MissingFlowLabelsError)
    assert re.search(r"grill.*mw flow seed-labels --team", str(refused.error))


def test_flow_labels_outside_the_group_do_not_count() -> None:
    tracker = FakeTicketTracker(LabelNames((LabelName("grill"),)), ())
    refused = FlowLabelCheck.require(tracker, FlowLabels.fake(), None)
    assert isinstance(refused, Err)
    assert isinstance(refused.error, MissingFlowLabelsError)


def test_a_team_holding_every_flow_label_passes() -> None:
    wanted = FlowLabels.fake()
    tracker = FakeTicketTracker(
        LabelNames(()), (), team_groups={(TeamKey.fake(), wanted.group): wanted.labels}
    )
    assert FlowLabelCheck.require(tracker, wanted, TeamKey.fake()) == Ok(None)


def test_a_team_without_flow_labels_falls_back_to_the_workspace() -> None:
    wanted = FlowLabels.fake()
    tracker = FakeTicketTracker(wanted.labels, (), groups={wanted.group: wanted.labels})
    assert FlowLabelCheck.require(tracker, wanted, TeamKey.fake()) == Ok(None)


def test_a_team_and_the_workspace_together_can_hold_the_flow_labels() -> None:
    wanted = FlowLabels.fake()
    in_team = LabelNames(wanted.labels.root[:1])
    in_workspace = LabelNames(wanted.labels.root[1:])
    tracker = FakeTicketTracker(
        in_workspace,
        (),
        groups={wanted.group: in_workspace},
        team_groups={(TeamKey.fake(), wanted.group): in_team},
    )
    assert FlowLabelCheck.require(tracker, wanted, TeamKey.fake()) == Ok(None)


def test_another_teams_flow_labels_do_not_count() -> None:
    wanted = FlowLabels.fake()
    tracker = FakeTicketTracker(
        LabelNames(()), (), team_groups={(TeamKey("OPS"), wanted.group): wanted.labels}
    )
    refused = FlowLabelCheck.require(tracker, wanted, TeamKey.fake())
    assert isinstance(refused, Err)
    assert isinstance(refused.error, MissingFlowLabelsError)


def test_a_team_flow_group_does_not_cover_the_workspace() -> None:
    wanted = FlowLabels.fake()
    tracker = FakeTicketTracker(
        LabelNames(()), (), team_groups={(TeamKey.fake(), wanted.group): wanted.labels}
    )
    refused = FlowLabelCheck.require(tracker, wanted, None)
    assert isinstance(refused, Err)
    assert isinstance(refused.error, MissingFlowLabelsError)
