from typing import TYPE_CHECKING

import pytest

from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTrackerError
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier, LabelName
from mb_workflow.c_infrastructure.credentials import MissingCredentialsError
from mb_workflow.c_infrastructure.lazy_linear import LazyLinear, LazyLinearClaims

if TYPE_CHECKING:
    from mb_workflow.c_infrastructure.linear import LinearApiKey


def missing_key() -> LinearApiKey:
    raise MissingCredentialsError("No Linear credentials for this repository.")


def test_a_lazy_registry_reads_no_key_until_it_is_used() -> None:
    claims = LazyLinearClaims(missing_key)
    with pytest.raises(TicketTrackerError, match="No Linear credentials"):
        _ = claims.claims(IssueIdentifier.fake())


def test_a_lazy_tracker_reads_no_key_until_it_is_used() -> None:
    tracker = LazyLinear(missing_key)
    with pytest.raises(TicketTrackerError, match="No Linear credentials"):
        tracker.remove_label(IssueIdentifier.fake(), LabelName("claimed"))
