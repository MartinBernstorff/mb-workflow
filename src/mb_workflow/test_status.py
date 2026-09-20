from mb_workflow.flow import StateName, StateNames
from mb_workflow.status import FakeStatusStore


def test_a_fresh_fake_store_sits_at_the_start_state() -> None:
    assert FakeStatusStore().read() == StateNames.start()


def test_the_fake_store_reads_back_what_it_was_given() -> None:
    assert FakeStatusStore(StateName("Merging")).read() == StateName("Merging")


def test_writing_moves_the_fake_store_to_the_new_state() -> None:
    store = FakeStatusStore()
    store.write(StateName("Implementing"))
    assert store.read() == StateName("Implementing")
