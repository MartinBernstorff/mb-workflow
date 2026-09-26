from typing import Protocol, override

from mb_workflow.b_core.d_domain_model.pool import PoolTickets


class TieBreak(Protocol):
    def shuffled(self, tickets: PoolTickets) -> PoolTickets: ...


class ReversingTieBreak(TieBreak):
    @override
    def shuffled(self, tickets: PoolTickets) -> PoolTickets:
        return PoolTickets(tuple(reversed(tickets.root)))
