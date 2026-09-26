from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.issue import LabelNames


def seed_flow_labels(tracker: TicketTracker, wanted: FlowLabels) -> LabelNames:
    missing = wanted.missing(tracker.group_labels(wanted.group))
    if missing.root:
        tracker.create_group_labels(wanted.group, missing)
    return missing
