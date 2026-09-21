from mb_workflow.b_core.flow import StateName
from mb_workflow.b_core.status import FakeStatusStore


def test_the_fake_store_reads_back_what_it_was_given() -> None:
    assert FakeStatusStore(StateName("Merging")).read() == StateName("Merging")


def test_writing_moves_the_fake_store_to_the_new_state() -> None:
    store = FakeStatusStore(StateName("Grilling"))
    store.write(StateName("Implementing"))
    assert store.read() == StateName("Implementing")
