from typing import TYPE_CHECKING, Protocol, override

from pydantic import NonNegativeInt

from mb_workflow.d_lib.models import Value

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.clock import IntervalSeconds


class Stopped(Value[bool]):
    @staticmethod
    def fake() -> Stopped:
        return Stopped(False)


class StopSignal(Protocol):
    def requested(self) -> Stopped: ...

    def wait(self, interval: IntervalSeconds) -> None: ...


class WaitCount(Value[NonNegativeInt]):
    @staticmethod
    def fake() -> WaitCount:
        return WaitCount(1)


class FakeStopSignal(StopSignal):
    def __init__(self, stop_on_wait: WaitCount | None = None) -> None:
        self._stop_on_wait = stop_on_wait
        self._waits = 0
        self._stopped = False

    def signal(self) -> None:
        self._stopped = True

    def waits(self) -> WaitCount:
        return WaitCount(self._waits)

    @override
    def requested(self) -> Stopped:
        return Stopped(self._stopped)

    @override
    def wait(self, interval: IntervalSeconds) -> None:
        if self._stopped:
            return
        self._waits += 1
        if self._stop_on_wait is not None and self._waits >= self._stop_on_wait.root:
            self._stopped = True
