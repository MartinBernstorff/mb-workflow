from contextlib import contextmanager
from typing import TYPE_CHECKING, Protocol, override

from safe_result import Err, Ok, Result

if TYPE_CHECKING:
    from collections.abc import Generator
    from contextlib import AbstractContextManager


class AlreadyRunningError(Exception):
    pass


# Acquiring returns the held lock to enter, so a run cannot reach its body without the lock.
class RunLock(Protocol):
    def acquire(self) -> Result[AbstractContextManager[None], AlreadyRunningError]: ...


class FakeRunLock(RunLock):
    def __init__(self) -> None:
        self._held = False

    @override
    def acquire(self) -> Result[AbstractContextManager[None], AlreadyRunningError]:
        if self._held:
            return Err(AlreadyRunningError("another run holds the lock"))
        self._held = True
        return Ok(self._released_on_exit())

    @contextmanager
    def _released_on_exit(self) -> Generator[None]:
        try:
            yield
        finally:
            self._held = False
