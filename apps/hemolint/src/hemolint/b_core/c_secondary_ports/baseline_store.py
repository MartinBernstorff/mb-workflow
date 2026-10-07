from typing import TYPE_CHECKING, Protocol, override

from safe_result import Ok, Result

from hemolint.b_core.d_domain_model.baseline import Baseline

if TYPE_CHECKING:
    from hemolint.b_core.d_domain_model.violation import LinterName


class BaselineStoreError(Exception):
    pass


# Linters can share one store, so each reads and writes only its own violations.
class BaselineStore(Protocol):
    def read(self, linter: LinterName) -> Result[Baseline, BaselineStoreError]: ...

    # Replaces the linter's whole baseline, so its violations missing from it are gone afterwards.
    def write(self, linter: LinterName, baseline: Baseline) -> Result[None, BaselineStoreError]: ...


class FakeBaselineStore(BaselineStore):
    def __init__(self, baseline: Baseline | None = None) -> None:
        self.baseline = baseline if baseline is not None else Baseline.of(())

    @override
    def read(self, linter: LinterName) -> Result[Baseline, BaselineStoreError]:
        return Ok(self.baseline.of_linter(linter))

    @override
    def write(self, linter: LinterName, baseline: Baseline) -> Result[None, BaselineStoreError]:
        others = (violation for violation in self.baseline.root if violation.file.linter != linter)
        self.baseline = Baseline.of((*others, *baseline.root))
        return Ok(None)
