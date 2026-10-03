from typing import TYPE_CHECKING, Protocol, override

from mb_workflow.b_core.d_domain_model.autolabel import Ledger

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.issue import LabelName


class LedgerStore(Protocol):
    def read(self, label: LabelName) -> Ledger: ...

    def write(self, label: LabelName, ledger: Ledger) -> None: ...


class FakeLedgerStore(LedgerStore):
    def __init__(self) -> None:
        self._ledgers: dict[LabelName, Ledger] = {}

    @override
    def read(self, label: LabelName) -> Ledger:
        return self._ledgers.get(label, Ledger(()))

    @override
    def write(self, label: LabelName, ledger: Ledger) -> None:
        self._ledgers[label] = ledger
