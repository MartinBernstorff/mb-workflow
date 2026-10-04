import logging
import signal
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, override

from pydantic import PositiveFloat

from mb_workflow.b_core.c_secondary_ports.stop_signal import Stopped, StopSignal
from mb_workflow.d_lib.models import Value

if TYPE_CHECKING:
    from collections.abc import Generator

    from mb_workflow.b_core.d_domain_model.clock import IntervalSeconds

logger = logging.getLogger(__name__)


class PollSeconds(Value[PositiveFloat]):
    @staticmethod
    def fake() -> PollSeconds:
        return PollSeconds(0.2)


class SignalStop(StopSignal):
    def __init__(self, poll: PollSeconds) -> None:
        self._poll = poll
        self._stopped = False

    @staticmethod
    @contextmanager
    def installed(poll: PollSeconds) -> Generator[SignalStop]:
        stop = SignalStop(poll)
        previous = {
            number: signal.signal(
                number, lambda received, _frame: stop.received(signal.Signals(received))
            )
            for number in (signal.SIGINT, signal.SIGTERM)
        }
        try:
            yield stop
        finally:
            for number, handler in previous.items():
                _ = signal.signal(number, handler)

    def received(self, number: signal.Signals) -> None:
        if self._stopped:
            raise SystemExit(128 + number.value)
        logger.info("Stopping once this pass ends; signal again to stop now.")
        self._stopped = True

    @override
    def requested(self) -> Stopped:
        return Stopped(self._stopped)

    @override
    def wait(self, interval: IntervalSeconds) -> None:
        deadline = time.monotonic() + interval.root
        while not self._stopped:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(remaining, self._poll.root))
