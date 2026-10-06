import logging
from typing import TYPE_CHECKING

from assertions import Assert

from mb_workflow.a_presentation.console import Output
from mb_workflow.a_presentation.drain_report import ConsoleDrainNarrator, DrainReport
from mb_workflow.b_core.a_features.autolabel import DryRun
from mb_workflow.b_core.a_features.drain import (
    Changed,
    DrainOutcome,
    LossReason,
    Lost,
    Override,
    PoolFull,
    Skip,
    Unready,
    UnreadyReason,
)
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
from mb_workflow.b_core.d_domain_model.issue import GroupedLabels, IssueIdentifier, Priority
from mb_workflow.b_core.d_domain_model.pool import (
    Limit,
    PoolTicket,
    PoolTickets,
    Refusal,
)

if TYPE_CHECKING:
    import pytest


def ticket(identifier: IssueIdentifier) -> PoolTicket:
    return PoolTicket.fake().model_copy(
        update={"issue": PoolTicket.fake().issue.model_copy(update={"identifier": identifier})}
    )


def nothing() -> DrainOutcome:
    return DrainOutcome(ready=PoolTickets(()), picked=PoolTickets(()), skipped=())


def summary_of(outcome: DrainOutcome, dry_run: DryRun = DryRun(False)) -> Output:
    return DrainReport.summary(outcome, FlowLabels.fake(), dry_run)


def test_the_summary_lists_each_ticket_with_its_priority_state_and_outcome() -> None:
    urgent = ticket(IssueIdentifier("MB-2")).model_copy(update={"priority": Priority.urgent})
    reason = UnreadyReason("it is already claimed")
    outcome = nothing().model_copy(
        update={
            "picked": PoolTickets((urgent,)),
            "unready": (Unready(ticket=ticket(IssueIdentifier("MB-1")), reason=reason),),
        }
    )
    Assert.that(summary_of(outcome)).matches(
        Output(
            "   Ticket  Priority  State  Outcome\n"
            "·  MB-1    medium    todo   not ready: it is already claimed\n"
            "✅ MB-2    urgent    todo   started\n"
            "\n"
            "Started 1 of 2.\n"
        )
    )


def test_the_summary_orders_tickets_by_number() -> None:
    nine = IssueIdentifier("MB-9")
    ten = IssueIdentifier("MB-10")
    outcome = nothing().model_copy(update={"picked": PoolTickets((ticket(ten), ticket(nine)))})
    lines = summary_of(outcome).root.splitlines()
    Assert.that(lines[1]).contains(nine.root)
    Assert.that(lines[2]).contains(ten.root)


def test_a_dry_run_summary_says_which_tickets_would_start() -> None:
    lines = summary_of(DrainOutcome.fake(), DryRun(True)).root.splitlines()
    Assert.that(lines[1]).ends_with("would start")
    Assert.that(lines[-1]).matches("Would start 1 of 2.")


def test_a_skipped_ticket_names_the_limit_that_refused_it() -> None:
    refusal = Refusal("label refactor is at its limit of 1")
    skip = Skip(ticket=PoolTicket.fake(), refusal=refusal)
    summary = summary_of(nothing().model_copy(update={"skipped": (skip,)}))
    Assert.that(summary.root).contains(f"·  {PoolTicket.fake().issue.identifier.root}")
    Assert.that(summary.root).contains(f"skipped: {refusal.root}")


def test_a_ticket_another_host_won_is_marked_lost() -> None:
    reason = LossReason("another host holds it")
    lost = Lost(ticket=PoolTicket.fake(), reason=reason)
    summary = summary_of(nothing().model_copy(update={"lost": (lost,)}))
    Assert.that(summary.root).contains(f"lost: {reason.root}")


def test_the_tickets_a_full_pool_left_are_marked_not_started() -> None:
    total = Limit(1)
    full = PoolFull(total=total, left=PoolTickets.fake())
    summary = summary_of(nothing().model_copy(update={"full": full}))
    Assert.that(summary.root).contains(f"not started: the pool is full at {total.root}")


def test_a_ticket_that_overrode_the_limits_says_which_limit() -> None:
    refusal = Refusal("grill is at its limit of 1")
    outcome = nothing().model_copy(
        update={
            "picked": PoolTickets.fake(),
            "overridden": (Override(ticket=PoolTicket.fake(), refusal=refusal),),
        }
    )
    Assert.that(summary_of(outcome).root).contains(f"started although {refusal.root}")


def test_a_ticket_without_a_flow_label_shows_as_stateless() -> None:
    unlabelled = PoolTicket.fake().model_copy(
        update={"issue": PoolTicket.fake().issue.model_copy(update={"grouped": GroupedLabels(())})}
    )
    outcome = nothing().model_copy(update={"picked": PoolTickets((unlabelled,))})
    Assert.that(summary_of(outcome).root.splitlines()[1]).contains("  -  ")


def test_a_pass_over_an_empty_view_prints_only_the_count() -> None:
    Assert.that(summary_of(nothing())).matches(Output("Started 0 of 0.\n"))


def test_an_unchanged_pass_logs_one_line(
    caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    quiet = DrainOutcome.fake().model_copy(update={"picked": PoolTickets(())})
    with caplog.at_level(logging.INFO):
        ConsoleDrainNarrator(FlowLabels.fake()).passed(quiet, Changed(False))
    Assert.that(caplog.messages).matches(["No change; 1 ready."])
    Assert.that(capsys.readouterr().out).matches("")


def test_a_changed_pass_prints_its_summary(capsys: pytest.CaptureFixture[str]) -> None:
    ConsoleDrainNarrator(FlowLabels.fake()).passed(DrainOutcome.fake(), Changed(True))
    Assert.that(capsys.readouterr().out).matches(summary_of(DrainOutcome.fake()).root)
