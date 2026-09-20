from typing import TYPE_CHECKING

import pytest

from mb_workflow.flow import StateName, StateNames
from mb_workflow.workspace.board import (
    BoardConfiguration,
    BoardError,
    Column,
    Columns,
    ConfigurationDocument,
    StateColumns,
    UserDataPath,
)
from mb_workflow.workspace.orca import ColumnLabel, WorkspaceStatus

if TYPE_CHECKING:
    from pathlib import Path


def board() -> Columns:
    return Columns(
        tuple(
            Column(id=WorkspaceStatus(f"status-{index}"), label=pairing.label)
            for index, pairing in enumerate(StateColumns.of_chart().root)
        )
    )


def test_reads_the_id_to_label_table_off_the_board_configuration() -> None:
    columns = BoardConfiguration.parse(ConfigurationDocument.fake()).columns()
    assert columns.label_of(WorkspaceStatus("status-5-2")) == ColumnLabel("Implementing")
    assert columns.id_of(ColumnLabel("Me reviewing others")) == WorkspaceStatus("status-8")


def test_a_board_with_no_columns_configured_parses() -> None:
    assert BoardConfiguration.parse(ConfigurationDocument('{"ui":{}}')).columns() == Columns(())


def test_an_id_the_board_does_not_define_has_no_label() -> None:
    columns = BoardConfiguration.parse(ConfigurationDocument.fake()).columns()
    assert columns.label_of(WorkspaceStatus("status-404")) is None


def test_every_state_the_chart_holds_has_a_board_column() -> None:
    assert (
        StateNames(frozenset(pairing.state for pairing in StateColumns.of_chart().root))
        == StateNames.of_chart()
    )


def test_a_column_id_resolves_to_the_state_its_label_stands_for() -> None:
    assert board().state_of(WorkspaceStatus("status-4")) == StateName("QA")


def test_a_column_outside_the_chart_reads_as_the_start_state() -> None:
    columns = Columns(
        (Column(id=WorkspaceStatus("status-8"), label=ColumnLabel("Me reviewing others")),)
    )
    assert columns.state_of(WorkspaceStatus("status-8")) == StateNames.start()


def test_a_workspace_with_no_column_reads_as_the_start_state() -> None:
    assert board().state_of(None) == StateNames.start()


def test_a_column_the_board_no_longer_defines_reads_as_the_start_state() -> None:
    assert board().state_of(WorkspaceStatus("status-404")) == StateNames.start()


def test_a_state_sits_in_the_board_column_its_label_names() -> None:
    assert board().column_for(StateName("Review")) == ColumnLabel("Awaiting review")


def test_a_state_the_board_has_no_column_for_is_a_clear_error() -> None:
    with pytest.raises(BoardError, match="no Archive column"):
        _ = Columns(()).column_for(StateName("Merged"))


def test_a_state_outside_the_chart_has_no_board_column() -> None:
    with pytest.raises(BoardError, match="no board column"):
        _ = StateColumns.of_chart().label_of(StateName("Abandoned"))


def test_the_board_configuration_sits_under_the_orca_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORCA_USER_DATA_PATH", str(UserDataPath.fake().root))
    assert UserDataPath.of_environment() == UserDataPath.fake()


def test_a_missing_user_data_path_is_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORCA_USER_DATA_PATH", raising=False)
    with pytest.raises(BoardError, match="ORCA_USER_DATA_PATH is unset"):
        _ = UserDataPath.of_environment()


def test_a_user_data_path_holding_no_profile_is_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(BoardError, match="no Orca profile"):
        _ = UserDataPath(tmp_path).configuration()


def test_a_user_data_path_holding_two_profiles_is_a_clear_error(tmp_path: Path) -> None:
    for profile in ("local-default", "work"):
        directory = tmp_path / "profiles" / profile
        directory.mkdir(parents=True)
        _ = (directory / "orca-data.json").write_text("{}")
    with pytest.raises(BoardError, match="more than one Orca profile"):
        _ = UserDataPath(tmp_path).configuration()


def test_reads_the_configuration_from_the_only_profile(tmp_path: Path) -> None:
    directory = tmp_path / "profiles" / "local-default"
    directory.mkdir(parents=True)
    _ = (directory / "orca-data.json").write_text(ConfigurationDocument.fake().root)
    document = UserDataPath(tmp_path).configuration().read()
    assert document == ConfigurationDocument.fake()
