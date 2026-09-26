import random
from typing import override

from mb_workflow.b_core.c_secondary_ports.tie_break import TieBreak
from mb_workflow.b_core.d_domain_model.pool import PoolTickets


class RandomTieBreak(TieBreak):
    @override
    def shuffled(self, tickets: PoolTickets) -> PoolTickets:
        return PoolTickets(tuple(random.sample(tickets.root, len(tickets.root))))
