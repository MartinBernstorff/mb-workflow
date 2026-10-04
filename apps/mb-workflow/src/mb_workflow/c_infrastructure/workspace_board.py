import re
from functools import cached_property
from typing import TYPE_CHECKING, override

from safe_result import Err, Ok, Result

from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore
from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManagerError
from mb_workflow.b_core.d_domain_model.flow import StateName
from mb_workflow.b_core.d_domain_model.workspace import WorkspaceStatus
from mb_workflow.c_infrastructure.orca import ColumnLabel, ErrorMessage, Orca
from mb_workflow.d_lib.models import Model, Payload, Value

if TYPE_CHECKING:
    from collections.abc import Callable

    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManager
    from mb_workflow.b_core.d_domain_model.workspace import Worktree


class BoardError(WorkspaceManagerError):
    pass


class Column(Payload):
    id: WorkspaceStatus
    label: ColumnLabel

    @staticmethod
    def fake() -> Column:
        return Column(id=WorkspaceStatus("status-5-2"), label=ColumnLabel.fake())


class WorkspaceStateColumn(Model):
    state: StateName
    label: ColumnLabel

    @staticmethod
    def fake() -> WorkspaceStateColumn:
        return WorkspaceStateColumn(state=StateName("implementing"), label=ColumnLabel.fake())


class StateColumns(Value[tuple[WorkspaceStateColumn, ...]]):
    @staticmethod
    def fake() -> StateColumns:
        return StateColumns((WorkspaceStateColumn.fake(),))

    @staticmethod
    def of_chart() -> StateColumns:
        return StateColumns(
            (
                WorkspaceStateColumn(state=StateName("grill"), label=ColumnLabel("Grilling")),
                WorkspaceStateColumn(state=StateName("to-ticket"), label=ColumnLabel("Speccing")),
                WorkspaceStateColumn(state=StateName("todo"), label=ColumnLabel("Tomorrow")),
                WorkspaceStateColumn(
                    state=StateName("implementing"), label=ColumnLabel("Implementing")
                ),
                WorkspaceStateColumn(state=StateName("qa"), label=ColumnLabel("My QA")),
                WorkspaceStateColumn(
                    state=StateName("review"), label=ColumnLabel("Awaiting review")
                ),
                WorkspaceStateColumn(state=StateName("merging"), label=ColumnLabel("Merging")),
                WorkspaceStateColumn(state=StateName("merged"), label=ColumnLabel("Merged")),
            )
        )

    def label_of(self, state: StateName) -> Result[ColumnLabel, BoardError]:
        for pairing in self.root:
            if pairing.state == state:
                return Ok(pairing.label)
        return Err(BoardError(f"{state.root} has no board column."))

    def state_of(self, label: ColumnLabel) -> StateName | None:
        for pairing in self.root:
            if pairing.label == label:
                return pairing.state
        return None


class Columns(Value[tuple[Column, ...]]):
    @staticmethod
    def fake() -> Columns:
        return Columns((Column.fake(),))

    @staticmethod
    def parse(refusal: ErrorMessage) -> Result[Columns, BoardError]:
        listed = re.findall(r"([\w-]+) \(([^)]+)\)", refusal.root.partition("Available:")[2])
        if not listed:
            return Err(BoardError(f"Orca named no board columns: {refusal.root}"))
        return Ok(
            Columns(
                tuple(
                    Column(id=WorkspaceStatus(status), label=ColumnLabel(label))
                    for status, label in listed
                )
            )
        )

    def label_of(self, status: WorkspaceStatus) -> ColumnLabel | None:
        for column in self.root:
            if column.id == status:
                return column.label
        return None

    def id_of(self, label: ColumnLabel) -> WorkspaceStatus | None:
        for column in self.root:
            if column.label == label:
                return column.id
        return None

    def status_for(self, state: StateName) -> Result[WorkspaceStatus, BoardError]:
        match StateColumns.of_chart().label_of(state):
            case Ok(label):
                pass
            case Err() as unmapped:
                return unmapped
        status = self.id_of(label)
        if status is None:
            return Err(
                BoardError(
                    f"The board defines no {label.root} column, so {state.root} cannot be recorded."
                )
            )
        return Ok(status)

    def state_of(self, status: WorkspaceStatus | None, start: StateName) -> StateName:
        if status is None:
            return start
        label = self.label_of(status)
        if label is None:
            return start
        state = StateColumns.of_chart().state_of(label)
        return state if state is not None else start


class WorkspaceBoard(WorkspaceStatusStore):
    def __init__(
        self,
        manager: WorkspaceManager,
        columns: Callable[[], Result[Columns, WorkspaceManagerError]],
        start: StateName,
        locate_worktree: Callable[[], Result[Worktree, WorkspaceManagerError]],
    ) -> None:
        self._manager = manager
        self._read_columns = columns
        self._start = start
        self._locate_worktree = locate_worktree

    @staticmethod
    def of_orca(orca: Orca, start: StateName) -> WorkspaceBoard:
        return WorkspaceBoard(orca, lambda: WorkspaceBoard.columns_of(orca), start, orca.current)

    @staticmethod
    def columns_of(orca: Orca) -> Result[Columns, WorkspaceManagerError]:
        match orca.columns(ColumnLabel.unknown()):
            case Ok(refusal):
                return Columns.parse(refusal)
            case Err() as failed:
                return failed

    def at(self, worktree: Worktree) -> WorkspaceBoard:
        return WorkspaceBoard(self._manager, self._read_columns, self._start, lambda: Ok(worktree))

    @cached_property
    def _columns(self) -> Result[Columns, WorkspaceManagerError]:
        return self._read_columns()

    @override
    def read(self) -> Result[StateName, WorkspaceManagerError]:
        match self._columns:
            case Ok(columns):
                pass
            case Err() as unread:
                return unread
        match self._locate_worktree():
            case Ok(here):
                return Ok(columns.state_of(here.status, self._start))
            case Err() as failed:
                return failed

    @override
    def write(self, state: StateName) -> Result[None, WorkspaceManagerError]:
        match self._locate_worktree():
            case Ok(here):
                pass
            case Err() as failed:
                return failed
        match self.status_for(state):
            case Ok(status):
                return self._manager.set_status(here.path, status)
            case Err() as unmapped:
                return unmapped

    @override
    def status_for(self, state: StateName) -> Result[WorkspaceStatus, WorkspaceManagerError]:
        match self._columns:
            case Ok(columns):
                return columns.status_for(state)
            case Err() as unread:
                return unread
