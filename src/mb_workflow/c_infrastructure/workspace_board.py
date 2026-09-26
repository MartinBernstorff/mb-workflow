import re
from functools import cached_property
from typing import override

from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore
from mb_workflow.b_core.d_domain_model.flow import StateName
from mb_workflow.b_core.d_domain_model.workspace import WorkspaceStatus
from mb_workflow.c_infrastructure.orca import ColumnLabel, ErrorMessage, Orca
from mb_workflow.d_lib.models import Model, Payload, Value


class BoardError(Exception):
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
        return WorkspaceStateColumn(state=StateName("Implementing"), label=ColumnLabel.fake())


class StateColumns(Value[tuple[WorkspaceStateColumn, ...]]):
    @staticmethod
    def fake() -> StateColumns:
        return StateColumns((WorkspaceStateColumn.fake(),))

    @staticmethod
    def of_chart() -> StateColumns:
        return StateColumns(
            (
                WorkspaceStateColumn(state=StateName("Grilling"), label=ColumnLabel("Grilling")),
                WorkspaceStateColumn(state=StateName("Speccing"), label=ColumnLabel("Speccing")),
                WorkspaceStateColumn(state=StateName("Specced"), label=ColumnLabel("Tomorrow")),
                WorkspaceStateColumn(
                    state=StateName("Implementing"), label=ColumnLabel("Implementing")
                ),
                WorkspaceStateColumn(state=StateName("QA"), label=ColumnLabel("My QA")),
                WorkspaceStateColumn(
                    state=StateName("Review"), label=ColumnLabel("Awaiting review")
                ),
                WorkspaceStateColumn(state=StateName("Merging"), label=ColumnLabel("Merging")),
                WorkspaceStateColumn(state=StateName("Merged"), label=ColumnLabel("Merged")),
            )
        )

    def label_of(self, state: StateName) -> ColumnLabel:
        for pairing in self.root:
            if pairing.state == state:
                return pairing.label
        raise BoardError(f"{state.root} has no board column.")

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
    def parse(refusal: ErrorMessage) -> Columns:
        listed = re.findall(r"([\w-]+) \(([^)]+)\)", refusal.root.partition("Available:")[2])
        if not listed:
            raise BoardError(f"Orca named no board columns: {refusal.root}")
        return Columns(
            tuple(
                Column(id=WorkspaceStatus(status), label=ColumnLabel(label))
                for status, label in listed
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

    def column_for(self, state: StateName) -> WorkspaceStatus:
        label = StateColumns.of_chart().label_of(state)
        status = self.id_of(label)
        if status is None:
            raise BoardError(
                f"The board defines no {label.root} column, so {state.root} cannot be recorded."
            )
        return status

    def state_of(self, status: WorkspaceStatus | None, start: StateName) -> StateName:
        if status is None:
            return start
        label = self.label_of(status)
        if label is None:
            return start
        state = StateColumns.of_chart().state_of(label)
        return state if state is not None else start


class WorkspaceBoard(WorkspaceStatusStore):
    def __init__(self, orca: Orca, start: StateName) -> None:
        self._orca = orca
        self._start = start

    # Read on first use, so a command that never touches the board never asks Orca for its columns.
    @cached_property
    def _columns(self) -> Columns:
        return Columns.parse(self._orca.columns(ColumnLabel.unknown()))

    @override
    def read(self) -> StateName:
        return self._columns.state_of(self._orca.current().status, self._start)

    @override
    def write(self, state: StateName) -> None:
        self._orca.set_status(self._orca.current().path, self.column_for(state))

    @override
    def column_for(self, state: StateName) -> WorkspaceStatus:
        return self._columns.column_for(state)
