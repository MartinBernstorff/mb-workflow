from pathlib import Path

from safe_result import Err

from hemolint.b_core.d_domain_model.violation import (
    Fingerprint,
    OutsideWorkingDirectoryError,
    SourceLine,
    SourcePath,
    WorkingDirectory,
)


def test_a_relative_source_path_stays_as_it_is() -> None:
    source = SourcePath(Path("src/a.py"))
    assert source.within(WorkingDirectory.fake()).unwrap() == source


def test_an_absolute_source_path_becomes_relative_to_the_working_directory() -> None:
    relative = Path("src/a.py")
    absolute = SourcePath(WorkingDirectory.fake().root / relative)
    assert absolute.within(WorkingDirectory.fake()).unwrap() == SourcePath(relative)


def test_a_source_path_that_climbs_out_of_the_working_directory_is_an_error() -> None:
    result = SourcePath(Path("src/../../a.py")).within(WorkingDirectory.fake())
    assert isinstance(result, Err)
    assert isinstance(result.error, OutsideWorkingDirectoryError)


def test_an_absolute_source_path_outside_the_working_directory_is_an_error() -> None:
    result = SourcePath(Path("/elsewhere/a.py")).within(WorkingDirectory.fake())
    assert isinstance(result, Err)


def test_a_fingerprint_is_the_source_line_without_surrounding_whitespace() -> None:
    code = "if x == None:"
    assert Fingerprint.of(SourceLine(f"    {code}  \n")) == Fingerprint(code)
