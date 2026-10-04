from typing import TYPE_CHECKING, Protocol, override

from safe_result import Err, Ok, Result

from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManagerError
from mb_workflow.b_core.d_domain_model.workspace import WorkspaceStatus

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.flow import StateName


class WorkspaceStatusStore(Protocol):
    def read(self) -> Result[StateName, WorkspaceManagerError]: ...

    def write(self, state: StateName) -> Result[None, WorkspaceManagerError]: ...

    def status_for(self, state: StateName) -> Result[WorkspaceStatus, WorkspaceManagerError]: ...


class FakeStatusStore(WorkspaceStatusStore):
    def __init__(self, state: StateName) -> None:
        self._state = state

    @override
    def read(self) -> Result[StateName, WorkspaceManagerError]:
        return Ok(self._state)

    @override
    def write(self, state: StateName) -> Result[None, WorkspaceManagerError]:
        self._state = state
        return Ok(None)

    @override
    def status_for(self, state: StateName) -> Result[WorkspaceStatus, WorkspaceManagerError]:
        return Ok(WorkspaceStatus(f"status-{state.root.casefold()}"))


class UnreachableStatusStore(WorkspaceStatusStore):
    def __init__(self) -> None:
        self._unreachable = WorkspaceManagerError("The workspace board is unreachable.")

    @override
    def read(self) -> Result[StateName, WorkspaceManagerError]:
        return Err(self._unreachable)

    @override
    def write(self, state: StateName) -> Result[None, WorkspaceManagerError]:
        return Err(self._unreachable)

    @override
    def status_for(self, state: StateName) -> Result[WorkspaceStatus, WorkspaceManagerError]:
        return Err(self._unreachable)
