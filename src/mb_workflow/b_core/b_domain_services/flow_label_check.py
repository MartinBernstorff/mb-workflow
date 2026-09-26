from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels


class MissingFlowLabelsError(Exception):
    pass


def require_flow_labels(tracker: TicketTracker, wanted: FlowLabels) -> None:
    missing = wanted.missing(tracker.group_labels(wanted.group))
    if missing.root:
        raise MissingFlowLabelsError(
            f"The {wanted.group.root} label group lacks"
            f" {', '.join(label.root for label in missing.root)}."
            " Run `mw flow seed-labels` to create them."
        )
