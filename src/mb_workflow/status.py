from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from mb_workflow.flow import StateName


class StatusStore(Protocol):
    def read(self) -> StateName: ...

    def write(self, state: StateName) -> None: ...


class FakeStatusStore:
    def __init__(self, state: StateName) -> None:
        self._state = state

    def read(self) -> StateName:
        return self._state

    def write(self, state: StateName) -> None:
        self._state = state
