from typing import Protocol

from mb_workflow.flow import StateName, StateNames


class StatusStore(Protocol):
    def read(self) -> StateName: ...

    def write(self, state: StateName) -> None: ...


class FakeStatusStore:
    def __init__(self, state: StateName | None = None) -> None:
        self._state = state if state is not None else StateNames.start()

    def read(self) -> StateName:
        return self._state

    def write(self, state: StateName) -> None:
        self._state = state
