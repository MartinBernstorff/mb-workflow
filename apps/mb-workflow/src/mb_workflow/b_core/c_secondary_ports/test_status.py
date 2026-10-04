from mb_workflow.b_core.c_secondary_ports.status import FakeStatusStore
from mb_workflow.b_core.d_domain_model.flow import StateName


def test_the_fake_store_reads_back_what_it_was_given() -> None:
    assert FakeStatusStore(StateName("merging")).read() == StateName("merging")


def test_writing_moves_the_fake_store_to_the_new_state() -> None:
    store = FakeStatusStore(StateName("grill"))
    store.write(StateName("implementing"))
    assert store.read() == StateName("implementing")


def test_the_fake_store_gives_each_state_its_own_status() -> None:
    store = FakeStatusStore(StateName("grill"))
    assert store.status_for(StateName("qa")) != store.status_for(StateName("review"))
