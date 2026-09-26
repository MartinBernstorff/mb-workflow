from mb_workflow.b_core.c_secondary_ports.status import FakeStatusStore
from mb_workflow.b_core.d_domain_model.flow import StateName


def test_the_fake_store_reads_back_what_it_was_given() -> None:
    assert FakeStatusStore(StateName("Merging")).read() == StateName("Merging")


def test_writing_moves_the_fake_store_to_the_new_state() -> None:
    store = FakeStatusStore(StateName("Grilling"))
    store.write(StateName("Implementing"))
    assert store.read() == StateName("Implementing")


def test_the_fake_store_gives_each_state_its_own_column() -> None:
    store = FakeStatusStore(StateName("Grilling"))
    assert store.column_for(StateName("QA")) != store.column_for(StateName("Review"))
