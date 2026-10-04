from assertions import Assert
from safe_result import Ok

from mb_workflow.b_core.c_secondary_ports.status import FakeStatusStore
from mb_workflow.b_core.d_domain_model.flow import StateName


def test_the_fake_store_reads_back_what_it_was_given() -> None:
    Assert.that(FakeStatusStore(StateName("merging")).read().unwrap()).matches(StateName("merging"))


def test_writing_moves_the_fake_store_to_the_new_state() -> None:
    implementing = StateName("implementing")
    store = FakeStatusStore(StateName("grill"))
    Assert.that(store.write(implementing)).matches(Ok(None))
    Assert.that(store.read().unwrap()).matches(implementing)


def test_the_fake_store_gives_each_state_its_own_status() -> None:
    store = FakeStatusStore(StateName("grill"))
    Assert.that(store.status_for(StateName("qa")).unwrap()).not_().matches(
        store.status_for(StateName("review")).unwrap()
    )
