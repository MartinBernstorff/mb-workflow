from contextlib import contextmanager
from typing import TYPE_CHECKING, Protocol, override

if TYPE_CHECKING:
    from collections.abc import Generator
    from contextlib import AbstractContextManager


class AlreadyRunningError(Exception):
    pass


class RunLock(Protocol):
    def held(self) -> AbstractContextManager[None]: ...


class FakeRunLock(RunLock):
    def __init__(self) -> None:
        self._held = False

    @override
    @contextmanager
    def held(self) -> Generator[None]:
        if self._held:
            raise AlreadyRunningError("another run holds the lock")
        self._held = True
        try:
            yield
        finally:
            self._held = False
