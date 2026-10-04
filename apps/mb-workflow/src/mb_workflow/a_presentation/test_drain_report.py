import logging
from typing import TYPE_CHECKING

from assertions import Assert

from mb_workflow.a_presentation.console import Output
from mb_workflow.a_presentation.drain_report import DrainReport, LoggingDrainNarrator
from mb_workflow.b_core.a_features.drain import (
    Changed,
    DrainOutcome,
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
    Assert.that(
        DrainReport.pick_listing(PoolTickets((urgent, unprioritised)), FlowLabels.fake())
    ).matches(Output("E-2\turgent\ttodo\nE-1\tno_priority\ttodo\n"))


def test_the_listing_marks_a_ticket_without_a_flow_label_as_stateless() -> None:
    unlabelled = PoolTicket.fake().model_copy(
        update={"issue": PoolTicket.fake().issue.model_copy(update={"grouped": GroupedLabels(())})}
    )
    Assert.that(
        DrainReport.pick_listing(PoolTickets((unlabelled,)), FlowLabels.fake()).root
    ).ends_with("\t-\n")


def test_each_skipped_ticket_is_logged_with_its_reason(caplog: pytest.LogCaptureFixture) -> None:
    skip = Skip(ticket=PoolTicket.fake(), refusal=Refusal("label refactor is at its limit of 1"))
    with caplog.at_level(logging.INFO):
        DrainReport.log_pass(DrainOutcome.fake().model_copy(update={"skipped": (skip,)}))
    Assert.that(
        f"Skipped {PoolTicket.fake().issue.identifier.root}: label refactor is at its limit of 1."
    ).in_container(caplog.messages)


def test_each_unready_ticket_is_logged_with_its_reason(caplog: pytest.LogCaptureFixture) -> None:
    reason = UnreadyReason("it is already claimed")
    unready = Unready(ticket=PoolTicket.fake(), reason=reason)
    with caplog.at_level(logging.INFO):
        DrainReport.log_pass(DrainOutcome.fake().model_copy(update={"unready": (unready,)}))
    Assert.that(f"Skipped {PoolTicket.fake().issue.identifier.root}: {reason.root}.").in_container(
        caplog.messages
    )


def test_a_full_pool_is_logged_with_the_tickets_it_left(caplog: pytest.LogCaptureFixture) -> None:
    total = Limit(1)
    full = PoolFull(total=total, left=PoolTickets.fake())
    with caplog.at_level(logging.INFO):
        DrainReport.log_pass(DrainOutcome.fake().model_copy(update={"full": full}))
    left = PoolTicket.fake().issue.identifier.root
    Assert.that(
        f"The pool is full at {total.root} tickets; leaving {left} unstarted."
    ).in_container(caplog.messages)


def test_an_unchanged_pass_logs_one_line(caplog: pytest.LogCaptureFixture) -> None:
    quiet = DrainOutcome.fake().model_copy(update={"picked": PoolTickets(())})
    with caplog.at_level(logging.INFO):
        LoggingDrainNarrator().passed(quiet, Changed(False))
    Assert.that(caplog.messages).matches(["No change; 1 ready."])


def test_a_changed_pass_logs_in_full(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        LoggingDrainNarrator().passed(DrainOutcome.fake(), Changed(True))
    identifier = PoolTicket.fake().issue.identifier.root
    Assert.that(f"Skipped {identifier}: {Refusal.fake().root}.").in_container(caplog.messages)
    Assert.that(f"Started {identifier}.").in_container(caplog.messages)
