import re
from pathlib import Path
from typing import override

from mb_workflow.b_core.c_secondary_ports.ledger_store import LedgerStore
from mb_workflow.b_core.d_domain_model.autolabel import Ledger
from mb_workflow.b_core.d_domain_model.cache import CacheDirectory
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier, LabelName
from mb_workflow.d_lib.models import Value


class LedgerText(Value[str]):
    @staticmethod
    def fake() -> LedgerText:
        return LedgerText.of(Ledger.fake())

    @staticmethod
    def of(ledger: Ledger) -> LedgerText:
        return LedgerText("".join(f"{issue.root}\n" for issue in ledger.root))

    def decode(self) -> Ledger:
        return Ledger(
            tuple(IssueIdentifier(line.strip()) for line in self.root.splitlines() if line.strip())
        )


class LedgerPath(Value[Path]):
    @staticmethod
    def fake() -> LedgerPath:
        return LedgerPath.of(CacheDirectory.fake(), LabelName.fake())

    @staticmethod
    def of(directory: CacheDirectory, label: LabelName) -> LedgerPath:
        name = re.sub(r"[^a-z0-9._-]+", "-", label.root.lower())
        return LedgerPath(directory.root / f"autolabel-{name}.txt")


class FileLedgerStore(LedgerStore):
    def __init__(self, directory: CacheDirectory) -> None:
        self._directory = directory

    @override
    def read(self, label: LabelName) -> Ledger:
        path = LedgerPath.of(self._directory, label).root
        if not path.is_file():
            return Ledger(())
        return LedgerText(path.read_text()).decode()

    @override
    def write(self, label: LabelName, ledger: Ledger) -> None:
        path = LedgerPath.of(self._directory, label).root
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(LedgerText.of(ledger).root)
