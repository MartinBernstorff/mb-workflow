from operator import attrgetter
from typing import TYPE_CHECKING

from mb_workflow.b_core.d_domain_model.issue import Priority
from mb_workflow.b_core.d_domain_model.pool import PoolTickets

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.tie_break import TieBreak
    from mb_workflow.b_core.d_domain_model.issue import LabelName


# Shuffling before a stable sort leaves the tie-break to order only tickets of equal priority.
def in_pick_order(
    tickets: PoolTickets, skip_limits_label: LabelName, tie_break: TieBreak
) -> PoolTickets:
    shuffled = tie_break.shuffled(tickets).root
    prioritised = sorted(
        (ticket for ticket in shuffled if ticket.priority != Priority.no_priority),
        key=attrgetter("priority"),
    )
    unprioritised = (ticket for ticket in shuffled if ticket.priority == Priority.no_priority)
    ordered = (*prioritised, *unprioritised)
    return PoolTickets(
        (
            *(ticket for ticket in ordered if ticket.skips_limits(skip_limits_label).root),
            *(ticket for ticket in ordered if not ticket.skips_limits(skip_limits_label).root),
        )
    )
