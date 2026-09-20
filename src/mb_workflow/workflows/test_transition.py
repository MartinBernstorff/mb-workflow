import pytest

from mb_workflow.flow import EventName, FlowError, StateName
from mb_workflow.shell import ExitCode
from mb_workflow.status import FakeStatusStore
from mb_workflow.workflows.transition import Force, transitioned


def test_a_legal_event_writes_the_target_state_to_the_store() -> None:
    store = FakeStatusStore(StateName("Implementing"))
    assert transitioned(store, EventName("qa"), Force(False)) == ExitCode(0)
    assert store.read() == StateName("QA")


def test_an_illegal_event_leaves_the_store_where_it_was() -> None:
    store = FakeStatusStore(StateName("Grilling"))
    with pytest.raises(FlowError, match="merge is not legal from Grilling"):
        _ = transitioned(store, EventName("merge"), Force(False))
    assert store.read() == StateName("Grilling")


def test_forcing_writes_the_target_state_without_validating() -> None:
    store = FakeStatusStore(StateName("Grilling"))
    assert transitioned(store, EventName("merged"), Force(True)) == ExitCode(0)
    assert store.read() == StateName("Merged")
