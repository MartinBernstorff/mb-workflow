from typing import Protocol, override

from safe_result import Ok, Result

from hemolint.b_core.d_domain_model.baseline import Baseline


class BaselineStoreError(Exception):
    pass


class BaselineStore(Protocol):
    def read(self) -> Result[Baseline, BaselineStoreError]: ...

    def write(self, baseline: Baseline) -> Result[None, BaselineStoreError]: ...


class FakeBaselineStore(BaselineStore):
    def __init__(self, baseline: Baseline | None = None) -> None:
        self.baseline = baseline if baseline is not None else Baseline.of(())

    @override
    def read(self) -> Result[Baseline, BaselineStoreError]:
        return Ok(self.baseline)

    @override
    def write(self, baseline: Baseline) -> Result[None, BaselineStoreError]:
        self.baseline = baseline
        return Ok(None)
