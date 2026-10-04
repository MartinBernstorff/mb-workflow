from enum import StrEnum
from pathlib import Path

import pytest
from safe_result import Err

from hemolint.b_core.c_secondary_ports.source_lines import FakeSourceLines, SourceLines
from hemolint.b_core.d_domain_model.violation import (
    LineNumber,
    MissingSourceLineError,
    SourceLine,
    SourcePath,
    SourceText,
    WorkingDirectory,
)
from hemolint.c_infrastructure.disk_source_lines import DiskSourceLines


class LinesKind(StrEnum):
    fake = "fake"
    disk = "disk"


source = SourcePath(Path("src/a.py"))
text = SourceText("x = 1\nif x == None:\n    pass\n")


@pytest.fixture(params=list(LinesKind))
def lines(request: pytest.FixtureRequest, tmp_path: Path) -> SourceLines:
    if LinesKind(request.param) == LinesKind.fake:
        return FakeSourceLines({source: text})
    (tmp_path / source.root).parent.mkdir(parents=True)
    _ = (tmp_path / source.root).write_text(text.root)
    return DiskSourceLines(WorkingDirectory(tmp_path))


def test_a_line_reads_by_its_one_based_number(lines: SourceLines) -> None:
    second = SourceLine("if x == None:")
    assert lines.read(source, LineNumber(2)).unwrap() == second


def test_a_line_past_the_end_of_the_file_is_an_error(lines: SourceLines) -> None:
    result = lines.read(source, LineNumber(4))
    assert isinstance(result, Err)
    assert isinstance(result.error, MissingSourceLineError)


def test_line_zero_is_an_error(lines: SourceLines) -> None:
    assert isinstance(lines.read(source, LineNumber(0)), Err)


def test_a_missing_source_file_is_an_error(lines: SourceLines) -> None:
    result = lines.read(SourcePath(Path("gone.py")), LineNumber(1))
    assert isinstance(result, Err)
    assert isinstance(result.error, MissingSourceLineError)
