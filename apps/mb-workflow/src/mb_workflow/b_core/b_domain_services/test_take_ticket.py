from typing import override

import pytest

from mb_workflow.b_core.b_domain_services.take_ticket import TicketTaking
from mb_workflow.b_core.c_secondary_ports.claims import (
    ClaimRefusedError,
    ClaimRequest,
    FakeClaimRegistry,
)
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
    FakeTicketTracker,
    TicketTrackerError,
    TrackedIssue,
)
from mb_workflow.b_core.d_domain_model.claim import Claims
from mb_workflow.b_core.d_domain_model.config import ClaimSettings, WorkspaceSettings
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier, LabelName, LabelNames


# Knows the claim label, yet fails to put it on a ticket, as Linear may.
class LabelRefusingTracker(FakeTicketTracker):
    @override
    def add_label(self, issue: IssueIdentifier, label: LabelName) -> None:
        raise TicketTrackerError(f"Linear refused the label {label.root}.")


def test_a_claim_that_cannot_be_labelled_is_withdrawn() -> None:
    tracker = LabelRefusingTracker(
        LabelNames((*LabelNames.fake().root, ClaimSettings.fake().label)), (TrackedIssue.fake(),)
    )
    claims = FakeClaimRegistry()
    with pytest.raises(ClaimRefusedError):
        TicketTaking.take_ticket(
            claims=claims,
            tracker=tracker,
            workspace=WorkspaceSettings.fake(),
            claim_settings=ClaimSettings.fake(),
            request=ClaimRequest.fake(),
            previous=None,
        ).unwrap()
    assert claims.claims(IssueIdentifier.fake()).unwrap() == Claims(())
