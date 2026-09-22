import pytest

from mb_workflow.b_core.b_domain_services.flow_transition import Force, transitioned
from mb_workflow.b_core.c_secondary_ports.status import FakeStatusStore
from mb_workflow.b_core.d_domain_model.flow import EventName, FlowError, StateName, WorkflowChart


def test_a_legal_event_writes_the_target_state_to_the_store() -> None:
    store = FakeStatusStore(StateName("Implementing"))
    assert transitioned(WorkflowChart, store, EventName("qa"), Force(False)) == StateName("QA")
    assert store.read() == StateName("QA")


def test_an_illegal_event_leaves_the_store_where_it_was() -> None:
    store = FakeStatusStore(StateName("Grilling"))
    with pytest.raises(FlowError, match="merge is not legal from Grilling"):
        _ = transitioned(WorkflowChart, store, EventName("merge"), Force(False))
    assert store.read() == StateName("Grilling")


def test_forcing_writes_the_target_state_without_validating() -> None:
    store = FakeStatusStore(StateName("Grilling"))
    assert transitioned(WorkflowChart, store, EventName("merged"), Force(True)) == StateName(
        "Merged"
    )
    assert store.read() == StateName("Merged")
