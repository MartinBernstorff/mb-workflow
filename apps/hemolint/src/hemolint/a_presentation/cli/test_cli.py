import json
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

source = "a.py"
rule = "CompareSingletonPrimitivesByIs"
code = "if x == None:"
violation = f"{source}@2:0 {rule}: Use `is`.\n"


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    _ = (tmp_path / source).write_text(f"x = 1\n{code}\n")
    return tmp_path


# Runs the installed entry point in the directory, since source paths are relative to it.
def run_hemolint(
    directory: Path, arguments: list[str], stdin: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", "from hemolint import main; main()", *arguments],
        cwd=directory,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def test_recording_a_baseline_exits_zero_and_says_what_it_added(workdir: Path) -> None:
    success = 0
    result = run_hemolint(workdir, ["check", "--format", "fixit", "--baseline"], violation)
    written = workdir / ".hemolint" / source / f"fixit-{rule}.json"
    assert result.returncode == success
    assert "Added 1" in result.stdout
    assert json.loads(written.read_text()) == {code: 1}


def test_another_directory_holds_the_baseline_when_given(workdir: Path) -> None:
    directory = "lint-baseline"
    _ = run_hemolint(
        workdir, ["check", "--format", "fixit", "--baseline", "--dir", directory], violation
    )
    assert (workdir / directory / source).is_dir()


def test_unparsable_output_exits_two_and_writes_nothing(workdir: Path) -> None:
    unparsable = 2
    result = run_hemolint(
        workdir,
        ["check", "--format", "fixit", "--baseline"],
        "b.py: EXCEPTION: Syntax Error @ 1:1.\n",
    )
    assert result.returncode == unparsable
    assert not (workdir / ".hemolint").exists()


def test_a_source_line_that_cannot_be_read_exits_one(workdir: Path) -> None:
    failure = 1
    result = run_hemolint(
        workdir, ["check", "--format", "fixit", "--baseline"], f"gone.py@1:0 {rule}: Use `is`.\n"
    )
    assert result.returncode == failure


def test_check_needs_a_format(workdir: Path) -> None:
    usage_error = 2
    result = run_hemolint(workdir, ["check", "--baseline"], "")
    assert result.returncode == usage_error
