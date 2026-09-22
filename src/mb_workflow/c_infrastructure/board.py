import re

from mb_workflow.b_core.d_domain_model.flow import StateName
from mb_workflow.c_infrastructure.orca import (
    ColumnLabel,
    ErrorMessage,
    Orca,
    WorkspaceStatus,
    WorktreeSelector,
)
from mb_workflow.d_lib.models import Model, Payload, Value


class BoardError(Exception):
    pass


class Column(Payload):
    id: WorkspaceStatus
    label: ColumnLabel

    @staticmethod
    def fake() -> Column:
        return Column(id=WorkspaceStatus("status-5-2"), label=ColumnLabel.fake())


class StateColumn(Model):
    state: StateName
    label: ColumnLabel

    @staticmethod
    def fake() -> StateColumn:
        return StateColumn(state=StateName("Implementing"), label=ColumnLabel.fake())


class StateColumns(Value[tuple[StateColumn, ...]]):
    @staticmethod
    def fake() -> StateColumns:
        return StateColumns((StateColumn.fake(),))

    @staticmethod
    def of_chart() -> StateColumns:
        return StateColumns(
            (
                StateColumn(state=StateName("Grilling"), label=ColumnLabel("Grilling")),
                StateColumn(state=StateName("Speccing"), label=ColumnLabel("Speccing")),
                StateColumn(state=StateName("Specced"), label=ColumnLabel("Tomorrow")),
                StateColumn(state=StateName("Implementing"), label=ColumnLabel("Implementing")),
                StateColumn(state=StateName("QA"), label=ColumnLabel("My QA")),
                StateColumn(state=StateName("Review"), label=ColumnLabel("Awaiting review")),
                StateColumn(state=StateName("Merging"), label=ColumnLabel("Merging")),
                StateColumn(state=StateName("Merged"), label=ColumnLabel("Merged")),
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

    def column_for(self, state: StateName) -> ColumnLabel:
        label = StateColumns.of_chart().label_of(state)
        if self.id_of(label) is None:
            raise BoardError(
                f"The board defines no {label.root} column, so {state.root} cannot be recorded."
            )
        return label

    def state_of(self, status: WorkspaceStatus | None, start: StateName) -> StateName:
        if status is None:
            return start
        label = self.label_of(status)
        if label is None:
            return start
        state = StateColumns.of_chart().state_of(label)
        return state if state is not None else start


class Board:
    def __init__(self, orca: Orca, columns: Columns, start: StateName) -> None:
        self._orca = orca
        self._columns = columns
        self._start = start

    @staticmethod
    def of_orca(orca: Orca, start: StateName) -> Board:
        return Board(orca, Columns.parse(orca.columns(ColumnLabel.unknown())), start)

    def read(self) -> StateName:
        return self._columns.state_of(self._orca.current().workspace_status, self._start)

    def write(self, state: StateName) -> None:
        self._orca.set_status(WorktreeSelector.current(), self._columns.column_for(state))
