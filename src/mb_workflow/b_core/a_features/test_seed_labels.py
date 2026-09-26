from mb_workflow.b_core.a_features.seed_labels import seed_flow_labels
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import FakeTicketTracker
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
from mb_workflow.b_core.d_domain_model.issue import LabelName, LabelNames


def empty_tracker() -> FakeTicketTracker:
    return FakeTicketTracker(LabelNames(()), ())


def test_seeding_creates_every_flow_label_in_the_group() -> None:
    tracker = empty_tracker()
    _ = seed_flow_labels(tracker, FlowLabels.fake())
    assert tracker.group_labels(FlowLabels.fake().group) == FlowLabels.fake().labels


def test_seeding_reports_the_labels_it_created() -> None:
    assert seed_flow_labels(empty_tracker(), FlowLabels.fake()) == FlowLabels.fake().labels


def test_seeding_again_changes_nothing() -> None:
    tracker = empty_tracker()
    _ = seed_flow_labels(tracker, FlowLabels.fake())
    assert (
        seed_flow_labels(tracker, FlowLabels.fake()),
        tracker.group_labels(FlowLabels.fake().group),
    ) == (LabelNames(()), FlowLabels.fake().labels)


def test_seeding_adds_only_the_labels_the_group_lacks() -> None:
    wanted = FlowLabels.fake()
    tracker = FakeTicketTracker(
        LabelNames((LabelName("Grilling"),)),
        (),
        groups={wanted.group: LabelNames((LabelName("Grilling"),))},
    )
    assert seed_flow_labels(tracker, wanted) == wanted.missing(LabelNames((LabelName("Grilling"),)))
