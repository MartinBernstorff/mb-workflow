from enum import StrEnum
from typing import TYPE_CHECKING

import pytest

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
    assert store.read(LabelName.fake()) == Ledger(())


def test_a_written_ledger_reads_back(store: LedgerStore) -> None:
    store.write(LabelName.fake(), ledger())
    assert store.read(LabelName.fake()) == ledger()


def test_an_empty_ledger_reads_back_empty(store: LedgerStore) -> None:
    store.write(LabelName.fake(), Ledger(()))
    assert store.read(LabelName.fake()) == Ledger(())


def test_a_second_write_replaces_the_first(store: LedgerStore) -> None:
    store.write(LabelName.fake(), ledger())
    store.write(LabelName.fake(), Ledger((IssueIdentifier("E-1"),)))
    assert store.read(LabelName.fake()) == Ledger((IssueIdentifier("E-1"),))


def test_each_label_keeps_its_own_ledger(store: LedgerStore) -> None:
    store.write(LabelName.fake(), ledger())
    assert store.read(LabelName("Backend")) == Ledger(())


def test_a_label_name_that_is_no_filename_still_gets_a_ledger(store: LedgerStore) -> None:
    store.write(LabelName("BE: needs/triage"), ledger())
    assert store.read(LabelName("BE: needs/triage")) == ledger()
