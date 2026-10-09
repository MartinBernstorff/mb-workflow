from collections import Counter
from datetime import UTC
from itertools import pairwise

from assertions import Assert
from hypothesis import given
from hypothesis import strategies as st

from mb_workflow.b_core.b_domain_services.pick_order import PickOrder
from mb_workflow.b_core.d_domain_model.issue import (
    IssueIdentifier,
    LabelName,
    LabelNames,
    Priority,
    UpdatedAt,
)
from mb_workflow.b_core.d_domain_model.pool import PoolTicket, PoolTickets, SkipsLimits
from mb_workflow.d_lib.models import Model

SKIP_LIMITS = LabelName("skip-limits")


def ticket(
    identifier: IssueIdentifier,
    priority: Priority,
    labels: LabelNames = LabelNames(()),
    updated_at: UpdatedAt = UpdatedAt.fake(),
) -> PoolTicket:
    return PoolTicket.fake().model_copy(
        update={
            "issue": PoolTicket.fake().issue.model_copy(
                update={"identifier": identifier, "labels": labels}
            ),
            "priority": priority,
            "updated_at": updated_at,
        }
    )


def picked(*tickets: PoolTicket) -> tuple[IssueIdentifier, ...]:
    return PickOrder.ordered(PoolTickets(tickets), SKIP_LIMITS).identifiers()


def test_a_ticket_labelled_skip_limits_comes_before_any_priority() -> None:
    Assert.that(
        picked(
            ticket(IssueIdentifier("MB-1"), Priority.urgent),
            ticket(
                IssueIdentifier("MB-2"),
                Priority.no_priority,
                LabelNames((LabelName("Skip-Limits"),)),
            ),
            ticket(IssueIdentifier("MB-3"), Priority.low, LabelNames((SKIP_LIMITS,))),
        )
    ).matches((IssueIdentifier("MB-3"), IssueIdentifier("MB-2"), IssueIdentifier("MB-1")))


def test_the_highest_priority_comes_first() -> None:
    Assert.that(
        picked(
            ticket(IssueIdentifier("MB-1"), Priority.low),
            ticket(IssueIdentifier("MB-2"), Priority.medium),
            ticket(IssueIdentifier("MB-3"), Priority.urgent),
            ticket(IssueIdentifier("MB-4"), Priority.high),
        )
    ).matches(
        (
            IssueIdentifier("MB-3"),
            IssueIdentifier("MB-4"),
            IssueIdentifier("MB-2"),
            IssueIdentifier("MB-1"),
        )
    )


def test_a_ticket_without_a_priority_comes_last() -> None:
    Assert.that(
        picked(
            ticket(IssueIdentifier("MB-1"), Priority.no_priority),
            ticket(IssueIdentifier("MB-2"), Priority.low),
        )
    ).matches((IssueIdentifier("MB-2"), IssueIdentifier("MB-1")))


def test_the_most_recently_updated_of_equal_priority_comes_first() -> None:
    oldest = UpdatedAt.fake()
    middle = oldest.later()
    newest = middle.later()
    Assert.that(
        picked(
            ticket(IssueIdentifier("MB-1"), Priority.high, updated_at=oldest),
            ticket(IssueIdentifier("MB-2"), Priority.high, updated_at=newest),
            ticket(IssueIdentifier("MB-3"), Priority.high, updated_at=middle),
        )
    ).matches((IssueIdentifier("MB-2"), IssueIdentifier("MB-3"), IssueIdentifier("MB-1")))


class TicketDraw(Model):
    priority: Priority
    skips_limits: SkipsLimits
    updated_at: UpdatedAt

    def ticket(self, identifier: IssueIdentifier) -> PoolTicket:
        return ticket(
            identifier,
            self.priority,
            LabelNames((SKIP_LIMITS,)) if self.skips_limits.root else LabelNames(()),
            self.updated_at,
        )

    @staticmethod
    def tickets() -> st.SearchStrategy[tuple[PoolTicket, ...]]:
        draw = st.builds(
            TicketDraw,
            priority=st.sampled_from(Priority),
            skips_limits=st.booleans().map(SkipsLimits),
            updated_at=st.datetimes(timezones=st.just(UTC)).map(UpdatedAt),
        )
        return st.lists(draw, max_size=12).map(
            lambda draws: tuple(
                drawn.ticket(IssueIdentifier(f"MB-{n}")) for n, drawn in enumerate(draws, 1)
            )
        )


def ordered(tickets: tuple[PoolTicket, ...]) -> tuple[PoolTicket, ...]:
    return PickOrder.ordered(PoolTickets(tickets), SKIP_LIMITS).root


def skips(ticket: PoolTicket) -> SkipsLimits:
    return ticket.skips_limits(SKIP_LIMITS)


@given(TicketDraw.tickets())
def test_the_order_holds_every_ticket_once(tickets: tuple[PoolTicket, ...]) -> None:
    Assert.that(Counter(ordered(tickets))).matches(Counter(tickets))


@given(TicketDraw.tickets())
def test_no_ticket_that_skips_the_limits_follows_one_that_does_not(
    tickets: tuple[PoolTicket, ...],
) -> None:
    for first, second in pairwise(ordered(tickets)):
        Assert.that(not skips(first).root and skips(second).root).matches(False)


@given(TicketDraw.tickets())
def test_no_ticket_follows_a_less_urgent_one_of_the_same_group(
    tickets: tuple[PoolTicket, ...],
) -> None:
    for first, second in pairwise(ordered(tickets)):
        if skips(first) != skips(second):
            continue
        Assert.that(
            (first.priority == Priority.no_priority and second.priority != Priority.no_priority)
            or (
                Priority.no_priority not in (first.priority, second.priority)
                and first.priority > second.priority
            )
        ).matches(False)


@given(TicketDraw.tickets())
def test_no_ticket_follows_an_older_one_of_the_same_group_and_priority(
    tickets: tuple[PoolTicket, ...],
) -> None:
    for first, second in pairwise(ordered(tickets)):
        if skips(first) != skips(second) or first.priority != second.priority:
            continue
        Assert.that(first.updated_at.root < second.updated_at.root).matches(False)
