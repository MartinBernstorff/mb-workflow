from mb_workflow.b_core.b_domain_services.pick_order import in_pick_order
from mb_workflow.b_core.c_secondary_ports.tie_break import ReversingTieBreak
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
from mb_workflow.b_core.d_domain_model.pool import PoolTicket, PoolTickets, Priority


def ticket(identifier: IssueIdentifier, priority: Priority) -> PoolTicket:
    return PoolTicket.fake().model_copy(
        update={
            "issue": PoolTicket.fake().issue.model_copy(update={"identifier": identifier}),
            "priority": priority,
        }
    )


def picked(*tickets: PoolTicket) -> tuple[IssueIdentifier, ...]:
    return in_pick_order(PoolTickets(tickets), ReversingTieBreak()).identifiers()


def test_the_highest_priority_comes_first() -> None:
    assert picked(
        ticket(IssueIdentifier("MB-1"), Priority.low),
        ticket(IssueIdentifier("MB-2"), Priority.medium),
        ticket(IssueIdentifier("MB-3"), Priority.urgent),
        ticket(IssueIdentifier("MB-4"), Priority.high),
    ) == (
        IssueIdentifier("MB-3"),
        IssueIdentifier("MB-4"),
        IssueIdentifier("MB-2"),
        IssueIdentifier("MB-1"),
    )


def test_a_ticket_without_a_priority_comes_last() -> None:
    assert picked(
        ticket(IssueIdentifier("MB-1"), Priority.no_priority),
        ticket(IssueIdentifier("MB-2"), Priority.low),
    ) == (
        IssueIdentifier("MB-2"),
        IssueIdentifier("MB-1"),
    )


def test_the_tie_break_orders_tickets_of_equal_priority() -> None:
    assert picked(
        ticket(IssueIdentifier("MB-1"), Priority.high),
        ticket(IssueIdentifier("MB-2"), Priority.urgent),
        ticket(IssueIdentifier("MB-3"), Priority.high),
    ) == (IssueIdentifier("MB-2"), IssueIdentifier("MB-3"), IssueIdentifier("MB-1"))
