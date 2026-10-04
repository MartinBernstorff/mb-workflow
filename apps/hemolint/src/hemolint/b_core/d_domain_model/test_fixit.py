from pathlib import Path

from safe_result import Err

from hemolint.b_core.d_domain_model.fixit import FixitParser
from hemolint.b_core.d_domain_model.linter_output import (
    LinterOutput,
    ReportedViolations,
    UnparsableLineError,
)
from hemolint.b_core.d_domain_model.violation import (
    LineNumber,
    ReportedViolation,
    RuleName,
    SourcePath,
)


def test_a_violation_line_parses_to_its_source_line_and_rule() -> None:
    source = Path("src/a.py")
    line = 12
    rule = "CompareSingletonPrimitivesByIs"
    output = LinterOutput(f"{source}@{line}:3 {rule}: Use `is` instead.\n")
    expected = ReportedViolations(
        (ReportedViolation(source=SourcePath(source), line=LineNumber(line), rule=RuleName(rule)),)
    )
    assert FixitParser.parse(output).unwrap() == expected


def test_a_message_with_an_autofix_note_still_parses() -> None:
    rule = "UseFstring"
    output = LinterOutput(f"a.py@1:0 {rule}: Use an f-string: a@b:1 c: d (has autofix)")
    assert FixitParser.parse(output).unwrap().root[0].rule == RuleName(rule)


def test_a_path_holding_an_at_sign_parses_whole() -> None:
    source = Path("pkg/@scope/a.py")
    output = LinterOutput(f"{source}@4:0 UseFstring: Use an f-string.")
    assert FixitParser.parse(output).unwrap().root[0].source == SourcePath(source)


def test_blank_lines_are_skipped() -> None:
    output = LinterOutput("\n  \na.py@1:0 UseFstring: Use an f-string.\n\n")
    assert len(FixitParser.parse(output).unwrap().root) == 1


def test_empty_output_holds_no_violations() -> None:
    assert FixitParser.parse(LinterOutput("")).unwrap() == ReportedViolations(())


def test_an_exception_line_is_a_parse_error() -> None:
    exception = "b.py: EXCEPTION: Syntax Error @ 1:1."
    output = LinterOutput(f"a.py@1:0 UseFstring: Use an f-string.\n{exception}\n")
    result = FixitParser.parse(output)
    assert isinstance(result, Err)
    assert isinstance(result.error, UnparsableLineError)
    assert exception in str(result.error)


def test_a_traceback_line_is_a_parse_error() -> None:
    output = LinterOutput("Traceback (most recent call last):")
    assert isinstance(FixitParser.parse(output), Err)
