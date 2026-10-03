import os
import signal
from enum import StrEnum
from typing import TYPE_CHECKING

import pytest

from mb_workflow.b_core.c_secondary_ports.stop_signal import FakeStopSignal, Stopped
from mb_workflow.b_core.d_domain_model.clock import IntervalSeconds
from mb_workflow.c_infrastructure.signal_stop import PollSeconds, SignalStop

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from mb_workflow.b_core.c_secondary_ports.stop_signal import StopSignal


class StopKind(StrEnum):
    fake = "fake"
    signal = "signal"


def send_sigterm() -> None:
    os.kill(os.getpid(), signal.SIGTERM)


@pytest.fixture(params=list(StopKind))
def stop_and_sender(
    request: pytest.FixtureRequest,
) -> Generator[tuple[StopSignal, Callable[[], None]]]:
    if StopKind(request.param) == StopKind.fake:
        fake = FakeStopSignal()
        yield fake, fake.signal
        return
    with SignalStop.installed(PollSeconds.fake()) as stop:
        yield stop, send_sigterm


def test_no_stop_is_requested_before_a_signal(
    stop_and_sender: tuple[StopSignal, Callable[[], None]],
) -> None:
    stop, _ = stop_and_sender
    assert stop.requested() == Stopped(False)


def test_a_stop_is_requested_after_a_signal(
    stop_and_sender: tuple[StopSignal, Callable[[], None]],
) -> None:
    stop, send = stop_and_sender
    send()
    assert stop.requested() == Stopped(True)


def test_a_wait_after_a_signal_returns_at_once(
    stop_and_sender: tuple[StopSignal, Callable[[], None]],
) -> None:
    stop, send = stop_and_sender
    send()
    stop.wait(IntervalSeconds(3600))
    assert stop.requested() == Stopped(True)


def test_a_second_signal_exits_at_once() -> None:
    with SignalStop.installed(PollSeconds.fake()):
        send_sigterm()
        with pytest.raises(SystemExit):
            send_sigterm()


def test_the_previous_handlers_return_once_the_block_ends() -> None:
    before = signal.getsignal(signal.SIGTERM)
    with SignalStop.installed(PollSeconds.fake()):
        pass
    assert signal.getsignal(signal.SIGTERM) == before
