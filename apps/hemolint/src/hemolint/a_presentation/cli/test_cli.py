import json
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from hemolint.a_presentation.cli import app

if TYPE_CHECKING:
    from pathlib import Path

check = ["check", "--format", "fixit", "--baseline"]


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    _ = (tmp_path / "a.py").write_text("x = 1\nif x == None:\n    pass\n")
    return tmp_path


def test_recording_a_baseline_exits_zero_and_says_what_it_added(workdir: Path) -> None:
    result = CliRunner().invoke(
        app, check, input="a.py@2:3 CompareSingletonPrimitivesByIs: Use `is`.\n"
    )
    written = workdir / ".hemolint" / "a.py" / "fixit-CompareSingletonPrimitivesByIs.json"
    assert result.exit_code == 0
    assert "Added 1" in result.output
    assert json.loads(written.read_text()) == {"if x == None:": 1}


def test_another_directory_holds_the_baseline_when_given(workdir: Path) -> None:
    directory = "lint-baseline"
    result = CliRunner().invoke(
        app,
        [*check, "--dir", directory],
        input="a.py@2:3 CompareSingletonPrimitivesByIs: Use `is`.\n",
    )
    assert result.exit_code == 0
    assert (workdir / directory / "a.py").is_dir()


def test_unparsable_output_exits_two_and_writes_nothing(workdir: Path) -> None:
    unparsable = 2
    result = CliRunner().invoke(app, check, input="b.py: EXCEPTION: Syntax Error @ 1:1.\n")
    assert result.exit_code == unparsable
    assert not (workdir / ".hemolint").exists()


@pytest.mark.usefixtures("workdir")
def test_check_needs_a_format() -> None:
    usage_error = 2
    result = CliRunner().invoke(app, ["check", "--baseline"], input="")
    assert result.exit_code == usage_error
