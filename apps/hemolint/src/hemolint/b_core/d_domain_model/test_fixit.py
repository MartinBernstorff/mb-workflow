from pathlib import Path

from safe_result import Err

from hemolint.b_core.d_domain_model.fixit import FixitParser
from hemolint.b_core.d_domain_model.linter_output import (
    LinterOutput,
    ReportedViolations,
    UnparsableOutputError,
)
from hemolint.b_core.d_domain_model.violation import (
    LineNumber,
    LinterLine,
    LocatedViolation,
    RuleName,
    SourcePath,
)


def test_a_violation_line_parses_to_its_source_line_and_rule() -> None:
    source = Path("src/a.py")
    line = 12
    rule = "CompareSingletonPrimitivesByIs"
    reported_as = f"{source}@{line}:3 {rule}: Use `is` instead."
    output = LinterOutput(f"{reported_as}\n")
    expected = ReportedViolations(
        (
            LocatedViolation(
                source=SourcePath(source),
                line=LineNumber(line),
                rule=RuleName(rule),
                reported_as=LinterLine(reported_as),
            ),
        )
    )
    assert FixitParser.parse(output).unwrap() == expected


def test_a_message_with_an_autofix_note_still_parses() -> None:
    rule = "UseFstring"
    output = LinterOutput(f"a.py@1:0 {rule}: Use an f-string: a@b:1 c: d (has autofix)")
    assert FixitParser.parse(output).unwrap().root[0].rule == RuleName(rule)


def test_a_path_holding_an_at_sign_parses_whole() -> None:
    source = Path("pkg/@scope/a.py")
    output = LinterOutput(f"{source}@4:0 UseFstring: Use an f-string.")
    violation = FixitParser.parse(output).unwrap().root[0]
    assert isinstance(violation, LocatedViolation)
    assert violation.source == SourcePath(source)


def test_blank_lines_are_skipped() -> None:
    violation = "a.py@1:0 UseFstring: Use an f-string."
    output = LinterOutput(f"\n  \n{violation}\n\n")
    assert FixitParser.parse(output).unwrap() == FixitParser.parse(LinterOutput(violation)).unwrap()


def test_empty_output_holds_no_violations() -> None:
    assert FixitParser.parse(LinterOutput("")).unwrap() == ReportedViolations(())


def test_an_exception_line_is_a_parse_error() -> None:
    exception = "b.py: EXCEPTION: Syntax Error @ 1:1."
    output = LinterOutput(f"a.py@1:0 UseFstring: Use an f-string.\n{exception}\n")
    result = FixitParser.parse(output)
    assert isinstance(result, Err)
    assert isinstance(result.error, UnparsableOutputError)
    assert exception in str(result.error)


def test_an_exception_line_whose_message_looks_like_a_violation_is_a_parse_error() -> None:
    output = LinterOutput("b.py: EXCEPTION: bad x@1:2 UseFstring: Use an f-string.")
    assert isinstance(FixitParser.parse(output), Err)


def test_a_traceback_line_is_a_parse_error() -> None:
    output = LinterOutput("Traceback (most recent call last):")
    assert isinstance(FixitParser.parse(output), Err)
