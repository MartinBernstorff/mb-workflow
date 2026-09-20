import os
from pathlib import Path

from mb_workflow.flow import StateName, StateNames
from mb_workflow.models import Model, Payload, Value
from mb_workflow.workspace.orca import ColumnLabel, Orca, WorkspaceStatus, WorktreeSelector


class BoardError(Exception):
    pass


class UserDataPath(Value[Path]):
    @staticmethod
    def fake() -> UserDataPath:
        return UserDataPath(Path("/Users/me/Library/Application Support/orca"))

    @staticmethod
    def of_environment() -> UserDataPath:
        directory = os.environ.get("ORCA_USER_DATA_PATH", "")
        if not directory:
            raise BoardError(
                "ORCA_USER_DATA_PATH is unset, so the board configuration cannot be found. "
                "Run this from a terminal Orca started."
            )
        return UserDataPath(Path(directory))

    def configuration(self) -> ConfigurationPath:
        profiles = sorted(self.root.glob("profiles/*/orca-data.json"))
        if not profiles:
            raise BoardError(f"{self.root} holds no Orca profile to read the board from.")
        if len(profiles) > 1:
            named = ", ".join(profile.parent.name for profile in profiles)
            raise BoardError(f"{self.root} holds more than one Orca profile: {named}.")
        return ConfigurationPath(profiles[0])


class ConfigurationPath(Value[Path]):
    @staticmethod
    def fake() -> ConfigurationPath:
        return ConfigurationPath(
            UserDataPath.fake().root / "profiles" / "local-default" / "orca-data.json"
        )

    def read(self) -> ConfigurationDocument:
        return ConfigurationDocument(self.root.read_text())


class ConfigurationDocument(Value[str]):
    @staticmethod
    def fake() -> ConfigurationDocument:
        return ConfigurationDocument(
            '{"ui":{"workspaceStatuses":['
            '{"id":"status-5-2","label":"Implementing"},'
            '{"id":"status-8","label":"Me reviewing others"}]}}'
        )


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
                StateColumn(state=StateName("Merged"), label=ColumnLabel("Archive")),
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

    def state_of(self, status: WorkspaceStatus | None) -> StateName:
        if status is None:
            return StateNames.start()
        label = self.label_of(status)
        if label is None:
            return StateNames.start()
        state = StateColumns.of_chart().state_of(label)
        return state if state is not None else StateNames.start()


class BoardUi(Payload):
    workspace_statuses: tuple[Column, ...] = ()

    @staticmethod
    def fake() -> BoardUi:
        return BoardUi(workspace_statuses=Columns.fake().root)


class BoardConfiguration(Payload):
    ui: BoardUi

    @staticmethod
    def fake() -> BoardConfiguration:
        return BoardConfiguration(ui=BoardUi.fake())

    @staticmethod
    def parse(document: ConfigurationDocument) -> BoardConfiguration:
        return BoardConfiguration.model_validate_json(document.root)

    def columns(self) -> Columns:
        return Columns(self.ui.workspace_statuses)


class Board:
    def __init__(self, orca: Orca, columns: Columns) -> None:
        self._orca = orca
        self._columns = columns

    @staticmethod
    def of_environment(orca: Orca) -> Board:
        document = UserDataPath.of_environment().configuration().read()
        return Board(orca, BoardConfiguration.parse(document).columns())

    def read(self) -> StateName:
        return self._columns.state_of(self._orca.current().workspace_status)

    def write(self, state: StateName) -> None:
        self._orca.set_status(WorktreeSelector.current(), self._columns.column_for(state))
