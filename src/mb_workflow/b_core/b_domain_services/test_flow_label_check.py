import pytest

from mb_workflow.b_core.b_domain_services.flow_label_check import (
    MissingFlowLabelsError,
    require_flow_labels,
)
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import FakeTicketTracker
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
from mb_workflow.b_core.d_domain_model.issue import LabelName, LabelNames


def test_a_tracker_holding_every_flow_label_passes() -> None:
    wanted = FlowLabels.fake()
    tracker = FakeTicketTracker(wanted.labels, (), groups={wanted.group: wanted.labels})
    require_flow_labels(tracker, wanted)


def test_a_missing_flow_label_fails_and_points_to_seed_labels() -> None:
    wanted = FlowLabels.fake()
    held = LabelNames(wanted.labels.root[1:])
    tracker = FakeTicketTracker(held, (), groups={wanted.group: held})
    with pytest.raises(MissingFlowLabelsError, match=r"Grilling.*mw flow seed-labels"):
        require_flow_labels(tracker, wanted)


def test_flow_labels_outside_the_group_do_not_count() -> None:
    tracker = FakeTicketTracker(LabelNames((LabelName("Grilling"),)), ())
    with pytest.raises(MissingFlowLabelsError):
        require_flow_labels(tracker, FlowLabels.fake())
