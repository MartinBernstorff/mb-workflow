from operator import attrgetter
from typing import TYPE_CHECKING

from mb_workflow.b_core.d_domain_model.issue import Priority
from mb_workflow.b_core.d_domain_model.pool import PoolTickets

if TYPE_CHECKING:
    from collections.abc import Iterable

    from mb_workflow.b_core.d_domain_model.issue import LabelName
    from mb_workflow.b_core.d_domain_model.pool import PoolTicket


class PickOrder:
    # Sorting newest first before the stable sorts leaves recency to order only tickets of equal
    # priority, so work continues on the tickets touched last.
    @staticmethod
    def ordered(tickets: PoolTickets, skip_limits_label: LabelName) -> PoolTickets:
        newest_first = sorted(tickets.root, key=attrgetter("updated_at.root"), reverse=True)
        return PoolTickets(
            (
                *PickOrder.by_priority(
                    ticket for ticket in newest_first if ticket.skips_limits(skip_limits_label).root
                ),
                *PickOrder.by_priority(
                    ticket
                    for ticket in newest_first
                    if not ticket.skips_limits(skip_limits_label).root
                ),
            )
        )

    @staticmethod
    def by_priority(tickets: Iterable[PoolTicket]) -> tuple[PoolTicket, ...]:
        listed = tuple(tickets)
        return (
            *sorted(
                (ticket for ticket in listed if ticket.priority != Priority.no_priority),
                key=attrgetter("priority"),
            ),
            *(ticket for ticket in listed if ticket.priority == Priority.no_priority),
        )
