from contextlib import contextmanager
from typing import TYPE_CHECKING, Protocol, override

from safe_result import Err, Ok, Result

if TYPE_CHECKING:
    from collections.abc import Generator
    from contextlib import AbstractContextManager


class AlreadyRunningError(Exception):
    pass


# Yields Err when another run holds the lock; the body then runs without holding it.
class RunLock(Protocol):
    def held(self) -> AbstractContextManager[Result[None, AlreadyRunningError]]: ...


class FakeRunLock(RunLock):
    def __init__(self) -> None:
        self._held = False

    @override
    @contextmanager
    def held(self) -> Generator[Result[None, AlreadyRunningError]]:
        if self._held:
            yield Err(AlreadyRunningError("another run holds the lock"))
            return
        self._held = True
        try:
            yield Ok(None)
        finally:
            self._held = False
