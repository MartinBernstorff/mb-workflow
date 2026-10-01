import logging
from typing import TYPE_CHECKING

from mb_workflow.a_presentation.console import Output
from mb_workflow.a_presentation.drain_report import log_skips, pick_listing
from mb_workflow.b_core.a_features.drain import DrainOutcome, Skip
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
from mb_workflow.b_core.d_domain_model.issue import GroupedLabels, IssueIdentifier
from mb_workflow.b_core.d_domain_model.pool import PoolTicket, PoolTickets, Priority, Refusal

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
        log_skips(DrainOutcome.fake().model_copy(update={"skipped": (skip,)}))
    assert (
        f"Skipped {PoolTicket.fake().issue.identifier.root}: label refactor is at its limit of 1."
        in caplog.messages
    )
