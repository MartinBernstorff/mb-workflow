import json
from pathlib import Path

from safe_result import Err

from hemolint.b_core.d_domain_model.linter_output import LinterOutput, UnparsableLineError
from hemolint.b_core.d_domain_model.ruff_json import ColumnNumber, RuffJsonParser, RuffMessage
from hemolint.b_core.d_domain_model.violation import (
    LineNumber,
    LinterLine,
    ReportedViolation,
    RuleName,
    SourcePath,
)


class RuffJson:
    # `ruff check --output-format json` with one violation, without the fields hemolint ignores.
    @staticmethod
    def output(
        filename: SourcePath,
        rule: RuleName | None,
        row: LineNumber | None = None,
        message: RuffMessage | None = None,
        column: ColumnNumber | None = None,
    ) -> LinterOutput:
        entry = {
            "code": None if rule is None else rule.root,
            "filename": str(filename.root),
            "location": {
                "column": (column or ColumnNumber.fake()).root,
                "row": (row or LineNumber.fake()).root,
            },
            "message": (message or RuffMessage.fake()).root,
            "name": "unused-import",
        }
        return LinterOutput(json.dumps([entry]))


def test_a_violation_parses_to_its_source_line_and_rule() -> None:
    filename = SourcePath(Path("/Users/me/project/src/a.py"))
    row = LineNumber(3)
    rule = RuleName("F401")
    message = RuffMessage("`os` imported but unused")
    column = ColumnNumber(8)
    output = RuffJson.output(filename, rule, row, message, column)
    expected = ReportedViolation(
        source=filename,
        line=row,
        rule=rule,
        reported_as=LinterLine(
            f"{filename.root}:{row.root}:{column.root}: {rule.root} {message.root}"
        ),
    )
    assert RuffJsonParser.parse(output).unwrap().root == (expected,)


def test_a_path_outside_the_working_directory_is_kept_as_reported() -> None:
    filename = SourcePath(Path("/elsewhere/a.py"))
    output = RuffJson.output(filename, RuleName.fake())
    assert RuffJsonParser.parse(output).unwrap().root[0].source == filename


def test_no_violations_parses_to_none() -> None:
    assert RuffJsonParser.parse(LinterOutput("[]")).unwrap().root == ()


def test_invalid_json_is_a_parse_error() -> None:
    result = RuffJsonParser.parse(LinterOutput("a.py:1:8: F401 `os` imported but unused"))
    assert isinstance(result, Err)
    assert isinstance(result.error, UnparsableLineError)


def test_json_without_a_rule_code_is_a_parse_error() -> None:
    output = RuffJson.output(SourcePath.fake(), None)
    assert isinstance(RuffJsonParser.parse(output), Err)
