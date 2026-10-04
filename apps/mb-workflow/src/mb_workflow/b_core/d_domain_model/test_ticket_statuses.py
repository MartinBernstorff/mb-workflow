import pytest

from mb_workflow.b_core.d_domain_model.flow import StateName
from mb_workflow.b_core.d_domain_model.issue import IssueStatusName
from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses


def test_a_complete_mapping_gives_each_flow_state_its_ticket_status() -> None:
    assert TicketStatuses.fake().of(StateName("review")) == IssueStatusName("In Review")


def test_a_state_in_another_case_maps_the_state_as_the_chart_spells_it() -> None:
    mapped = "In Review"
    table = {state.root: status.root for state, status in TicketStatuses.fake().root.items()}
    del table["review"]
    parsed = TicketStatuses.model_validate({**table, "Review": mapped})
    assert parsed.of(StateName("review")) == IssueStatusName(mapped)


def test_a_state_named_twice_in_different_cases_is_refused() -> None:
    table = {state.root: status.root for state, status in TicketStatuses.fake().root.items()}
    typed = "Review"
    with pytest.raises(ValueError, match=f"review, {typed} both map review"):
        _ = TicketStatuses.model_validate({**table, typed: "In Review"})


def test_a_mapping_with_a_gap_is_refused_naming_the_missing_flow_states() -> None:
    gapped = {
        state.root: status.root
        for state, status in TicketStatuses.fake().root.items()
        if state.root not in {"qa", "merged"}
    }
    with pytest.raises(ValueError, match="lacks qa, merged"):
        _ = TicketStatuses.model_validate(gapped)


def test_a_mapping_naming_a_former_state_is_refused() -> None:
    table = {state.root: status.root for state, status in TicketStatuses.fake().root.items()}
    former = "Specced"
    with pytest.raises(ValueError, match=f"The chart has no state named {former}"):
        _ = TicketStatuses.model_validate({**table, former: "Todo"})
