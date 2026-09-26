from typing import TYPE_CHECKING, Protocol, override

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.flow import StateName


class StatusStore(Protocol):
    def read(self) -> StateName: ...

    def write(self, state: StateName) -> None: ...


class FakeStatusStore(StatusStore):
    def __init__(self, state: StateName) -> None:
        self._state = state

    @override
    def read(self) -> StateName:
        return self._state

    @override
    def write(self, state: StateName) -> None:
        self._state = state
