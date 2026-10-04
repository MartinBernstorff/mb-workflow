from enum import StrEnum
from typing import TYPE_CHECKING

import pytest
from assertions import Assert

from mb_workflow.b_core.c_secondary_ports.ledger_store import FakeLedgerStore
from mb_workflow.b_core.d_domain_model.autolabel import Ledger
from mb_workflow.b_core.d_domain_model.cache import CacheDirectory
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier, LabelName
from mb_workflow.c_infrastructure.ledger_file import FileLedgerStore

if TYPE_CHECKING:
    from pathlib import Path

    from mb_workflow.b_core.c_secondary_ports.ledger_store import LedgerStore


class StoreKind(StrEnum):
    fake = "fake"
    file = "file"


@pytest.fixture(params=list(StoreKind))
def store(request: pytest.FixtureRequest, tmp_path: Path) -> LedgerStore:
    if StoreKind(request.param) == StoreKind.fake:
        return FakeLedgerStore()
    return FileLedgerStore(CacheDirectory(tmp_path / "cache"))


def ledger() -> Ledger:
    return Ledger((IssueIdentifier("E-4"), IssueIdentifier("E-11")))


def test_a_label_never_written_reads_as_an_empty_ledger(store: LedgerStore) -> None:
    Assert.that(store.read(LabelName.fake())).matches(Ledger(()))


def test_a_written_ledger_reads_back(store: LedgerStore) -> None:
    store.write(LabelName.fake(), ledger())
    Assert.that(store.read(LabelName.fake())).matches(ledger())


def test_an_empty_ledger_reads_back_empty(store: LedgerStore) -> None:
    store.write(LabelName.fake(), Ledger(()))
    Assert.that(store.read(LabelName.fake())).matches(Ledger(()))


def test_a_second_write_replaces_the_first(store: LedgerStore) -> None:
    store.write(LabelName.fake(), ledger())
    replacement = Ledger((IssueIdentifier("E-1"),))
    store.write(LabelName.fake(), replacement)
    Assert.that(store.read(LabelName.fake())).matches(replacement)


def test_each_label_keeps_its_own_ledger(store: LedgerStore) -> None:
    store.write(LabelName.fake(), ledger())
    Assert.that(store.read(LabelName("Backend"))).matches(Ledger(()))


def test_a_label_name_that_is_no_filename_still_gets_a_ledger(store: LedgerStore) -> None:
    label = LabelName("BE: needs/triage")
    store.write(label, ledger())
    Assert.that(store.read(label)).matches(ledger())
