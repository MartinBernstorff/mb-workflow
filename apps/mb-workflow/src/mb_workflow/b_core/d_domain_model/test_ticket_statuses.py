import pytest

from mb_workflow.b_core.d_domain_model.flow import StateName
from mb_workflow.b_core.d_domain_model.issue import IssueStatusName
from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses


def test_a_complete_mapping_gives_each_flow_state_its_ticket_status() -> None:
    assert TicketStatuses.fake().of(StateName("Review")) == IssueStatusName("In Review")


def test_a_mapping_with_a_gap_is_refused_naming_the_missing_flow_states() -> None:
    gapped = {
        state.root: status.root
        for state, status in TicketStatuses.fake().root.items()
        if state.root not in {"QA", "Merged"}
    }
    with pytest.raises(ValueError, match="lacks QA, Merged"):
        _ = TicketStatuses.model_validate(gapped)


def test_a_mapping_naming_a_state_outside_the_chart_is_refused() -> None:
    table = {state.root: status.root for state, status in TicketStatuses.fake().root.items()}
    with pytest.raises(ValueError, match="The chart has no state named Todo"):
        _ = TicketStatuses.model_validate({**table, "Todo": "Todo"})
