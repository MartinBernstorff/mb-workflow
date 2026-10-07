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


class HemolintProcess:
    # Runs the installed entry point in the directory, since source paths are relative to it.
    @staticmethod
    def run_in(
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
    result = HemolintProcess.run_in(
        workdir, ["check", "--format", "fixit", "--baseline"], violation
    )
    written = workdir / ".hemolint" / f"fixit-{rule}" / f"{source}.json"
    added = "Added 1"
    assert result.returncode == success
    assert added in result.stdout
    assert json.loads(written.read_text()) == {code: 1}


def test_ruff_json_with_absolute_paths_records_them_relative_to_the_working_directory(
    workdir: Path,
) -> None:
    ruff_rule = "E711"
    entry = {
        "code": ruff_rule,
        "filename": str(workdir / source),
        "location": {"column": 6, "row": 2},
        "message": "Comparison to `None` should be `cond is None`",
    }
    _ = HemolintProcess.run_in(
        workdir, ["check", "--format", "ruff-json", "--baseline"], json.dumps([entry])
    )
    written = workdir / ".hemolint" / f"ruff-{ruff_rule}" / f"{source}.json"
    assert json.loads(written.read_text()) == {code: 1}


def test_pyrefly_json_records_its_errors_by_rule(workdir: Path) -> None:
    pyrefly_rule = "bad-assignment"
    error = {
        "line": 2,
        "column": 4,
        "stop_line": 2,
        "stop_column": 13,
        "path": source,
        "name": pyrefly_rule,
        "concise_description": "`bool` is not assignable to `None`",
        "severity": "error",
    }
    _ = HemolintProcess.run_in(
        workdir, ["check", "--format", "pyrefly", "--baseline"], json.dumps({"errors": [error]})
    )
    written = workdir / ".hemolint" / f"pyrefly-{pyrefly_rule}" / f"{source}.json"
    assert json.loads(written.read_text()) == {code: 1}


def test_linters_sharing_a_baseline_directory_leave_each_other_alone(workdir: Path) -> None:
    success = 0
    error = {
        "line": 2,
        "column": 0,
        "stop_line": 2,
        "stop_column": 1,
        "path": source,
        "name": "bad-assignment",
        "concise_description": "`bool` is not assignable to `None`",
        "severity": "error",
    }
    _ = HemolintProcess.run_in(workdir, ["check", "--format", "fixit", "--baseline"], violation)
    _ = HemolintProcess.run_in(
        workdir, ["check", "--format", "pyrefly", "--baseline"], json.dumps({"errors": [error]})
    )
    checked = HemolintProcess.run_in(workdir, ["check", "--format", "fixit"], violation)
    pruned = HemolintProcess.run_in(workdir, ["check", "--format", "fixit", "--prune"], violation)
    assert checked.returncode == success
    assert pruned.returncode == success
    assert (workdir / ".hemolint" / f"fixit-{rule}" / f"{source}.json").is_file()
    assert (workdir / ".hemolint" / "pyrefly-bad-assignment" / f"{source}.json").is_file()


def test_another_directory_holds_the_baseline_when_given(workdir: Path) -> None:
    directory = "lint-baseline"
    _ = HemolintProcess.run_in(
        workdir, ["check", "--format", "fixit", "--baseline", "--dir", directory], violation
    )
    assert (workdir / directory / f"fixit-{rule}" / f"{source}.json").is_file()


def test_unparsable_output_exits_two_and_writes_nothing(workdir: Path) -> None:
    unparsable = 2
    result = HemolintProcess.run_in(
        workdir,
        ["check", "--format", "fixit", "--baseline"],
        "b.py: EXCEPTION: Syntax Error @ 1:1.\n",
    )
    assert result.returncode == unparsable
    assert not (workdir / ".hemolint").exists()


def test_a_source_line_that_cannot_be_read_exits_one(workdir: Path) -> None:
    failure = 1
    result = HemolintProcess.run_in(
        workdir, ["check", "--format", "fixit", "--baseline"], f"gone.py@1:0 {rule}: Use `is`.\n"
    )
    assert result.returncode == failure


def test_a_baseline_matching_the_violations_exits_zero(workdir: Path) -> None:
    success = 0
    _ = HemolintProcess.run_in(workdir, ["check", "--format", "fixit", "--baseline"], violation)
    result = HemolintProcess.run_in(workdir, ["check", "--format", "fixit"], violation)
    assert result.returncode == success


def test_a_fixed_violation_exits_one_and_is_listed_with_a_prune_hint(workdir: Path) -> None:
    failure = 1
    fixed_line = f"{source}: fixit-{rule} ×1 fixed"  # noqa: RUF001
    prune_hint = "hemolint check --prune"
    summary = "0 new and 1 fixed violations."
    _ = HemolintProcess.run_in(workdir, ["check", "--format", "fixit", "--baseline"], violation)
    result = HemolintProcess.run_in(workdir, ["check", "--format", "fixit"], "")
    assert result.returncode == failure
    assert fixed_line in result.stdout
    assert prune_hint in result.stdout
    assert result.stdout.endswith(f"{summary}\n")


def test_a_new_violation_exits_one_and_is_printed_as_the_linter_line(workdir: Path) -> None:
    failure = 1
    _ = HemolintProcess.run_in(workdir, ["check", "--format", "fixit", "--baseline"], "")
    result = HemolintProcess.run_in(workdir, ["check", "--format", "fixit"], violation)
    assert result.returncode == failure
    assert violation in result.stdout


def test_pruning_a_fixed_violation_exits_zero_and_removes_its_directory(workdir: Path) -> None:
    success = 0
    removed = "Removed 1 fixed violations"
    _ = HemolintProcess.run_in(workdir, ["check", "--format", "fixit", "--baseline"], violation)
    result = HemolintProcess.run_in(workdir, ["check", "--format", "fixit", "--prune"], "")
    assert result.returncode == success
    assert removed in result.stdout
    assert not (workdir / ".hemolint" / source).exists()


def test_pruning_with_a_new_violation_exits_one_and_does_not_record_it(workdir: Path) -> None:
    failure = 1
    result = HemolintProcess.run_in(workdir, ["check", "--format", "fixit", "--prune"], violation)
    assert result.returncode == failure
    assert violation in result.stdout
    assert not (workdir / ".hemolint" / source).exists()


def test_prune_and_baseline_together_is_a_usage_error(workdir: Path) -> None:
    usage_error = 2
    result = HemolintProcess.run_in(
        workdir, ["check", "--format", "fixit", "--prune", "--baseline"], ""
    )
    assert result.returncode == usage_error


def test_check_needs_a_format(workdir: Path) -> None:
    usage_error = 2
    result = HemolintProcess.run_in(workdir, ["check", "--baseline"], "")
    assert result.returncode == usage_error


def test_tach_json_records_located_and_global_violations(workdir: Path) -> None:
    located_kind, global_kind = "UndeclaredDependency", "UnusedDependencies"
    located_details = {"Code": {located_kind: {"dependency": "b.x"}}}
    global_details = {"Code": {global_kind: {"dependency": "b"}}}
    output = [
        {
            "Located": {
                "file_path": source,
                "line_number": 2,
                "original_line_number": 2,
                "severity": "Error",
                "details": located_details,
            }
        },
        {"Global": {"severity": "Warning", "details": global_details}},
    ]
    result = HemolintProcess.run_in(
        workdir, ["check", "--format", "tach", "--baseline"], json.dumps(output)
    )
    success = 0
    assert result.returncode == success
    located = workdir / ".hemolint" / f"tach-{located_kind}" / f"{source}.json"
    assert json.loads(located.read_text()) == {code: 1}
    assert (workdir / ".hemolint" / f"tach-{global_kind}" / "_global.json").is_file()


def test_a_tach_error_exits_two_and_writes_nothing(workdir: Path) -> None:
    unparsable = 2
    result = HemolintProcess.run_in(
        workdir,
        ["check", "--format", "tach", "--baseline"],
        json.dumps({"error": "Circular dependency", "dependencies": ["a", "b"]}),
    )
    assert result.returncode == unparsable
    assert not (workdir / ".hemolint").exists()
