import logging
from typing import TYPE_CHECKING

from mb_workflow.a_presentation.console import Output
from mb_workflow.a_presentation.drain_report import LoggingDrainNarrator, log_pass, pick_listing
from mb_workflow.b_core.a_features.drain import (
    Changed,
    DrainOutcome,
    PoolFull,
    Skip,
    Unready,
    UnreadyReason,
)
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
from mb_workflow.b_core.d_domain_model.issue import GroupedLabels, IssueIdentifier
from mb_workflow.b_core.d_domain_model.pool import (
    Limit,
    PoolTicket,
    PoolTickets,
    Priority,
    Refusal,
)

if TYPE_CHECKING:
    import pytest


def test_the_listing_names_each_ready_ticket_its_priority_and_state_in_order() -> None:
    urgent = PoolTicket.fake().model_copy(
        update={
            "issue": PoolTicket.fake().issue.model_copy(
                update={"identifier": IssueIdentifier("E-2")}
            ),
            "priority": Priority.urgent,
        }
    )
    unprioritised = PoolTicket.fake().model_copy(
        update={
            "issue": PoolTicket.fake().issue.model_copy(
                update={"identifier": IssueIdentifier("E-1")}
            ),
            "priority": Priority.no_priority,
        }
    )
    assert pick_listing(PoolTickets((urgent, unprioritised)), FlowLabels.fake()) == Output(
        "E-2\turgent\tSpecced\nE-1\tno_priority\tSpecced\n"
    )


def test_the_listing_marks_a_ticket_without_a_flow_label_as_stateless() -> None:
    unlabelled = PoolTicket.fake().model_copy(
        update={"issue": PoolTicket.fake().issue.model_copy(update={"grouped": GroupedLabels(())})}
    )
    assert pick_listing(PoolTickets((unlabelled,)), FlowLabels.fake()).root.endswith("\t-\n")


def test_each_skipped_ticket_is_logged_with_its_reason(caplog: pytest.LogCaptureFixture) -> None:
    skip = Skip(ticket=PoolTicket.fake(), refusal=Refusal("label refactor is at its limit of 1"))
    with caplog.at_level(logging.INFO):
        log_pass(DrainOutcome.fake().model_copy(update={"skipped": (skip,)}))
    assert (
        f"Skipped {PoolTicket.fake().issue.identifier.root}: label refactor is at its limit of 1."
        in caplog.messages
    )


def test_each_unready_ticket_is_logged_with_its_reason(caplog: pytest.LogCaptureFixture) -> None:
    unready = Unready(ticket=PoolTicket.fake(), reason=UnreadyReason("it is already claimed"))
    with caplog.at_level(logging.INFO):
        log_pass(DrainOutcome.fake().model_copy(update={"unready": (unready,)}))
    assert (
        f"Skipped {PoolTicket.fake().issue.identifier.root}: it is already claimed."
        in caplog.messages
    )


def test_a_full_pool_is_logged_with_the_tickets_it_left(caplog: pytest.LogCaptureFixture) -> None:
    full = PoolFull(total=Limit(1), left=PoolTickets.fake())
    with caplog.at_level(logging.INFO):
        log_pass(DrainOutcome.fake().model_copy(update={"full": full}))
    assert (
        f"The pool is full at 1 tickets; leaving {PoolTicket.fake().issue.identifier.root} unstarted."
        in caplog.messages
    )


def test_an_unchanged_pass_logs_one_line(caplog: pytest.LogCaptureFixture) -> None:
    quiet = DrainOutcome.fake().model_copy(update={"picked": PoolTickets(())})
    with caplog.at_level(logging.INFO):
        LoggingDrainNarrator().passed(quiet, Changed(False))
    assert caplog.messages == [f"No change; {len(quiet.ready.root)} ready."]


def test_a_changed_pass_logs_in_full(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        LoggingDrainNarrator().passed(DrainOutcome.fake(), Changed(True))
    assert (
        f"Skipped {PoolTicket.fake().issue.identifier.root}: {Refusal.fake().root}."
        in caplog.messages
    )
