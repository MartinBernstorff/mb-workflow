import json
from pathlib import Path

from safe_result import Err

from hemolint.b_core.d_domain_model.linter_output import LinterOutput, UnparsableOutputError
from hemolint.b_core.d_domain_model.ruff_json import RuffJsonParser, RuffMessage
from hemolint.b_core.d_domain_model.violation import (
    LineNumber,
    LinterLine,
    LocatedViolation,
    RuleName,
    SourcePath,
)


class RuffJson:
    @staticmethod
    def output(filename: SourcePath, rule: RuleName | None) -> LinterOutput:
        entry = {
            "code": None if rule is None else rule.root,
            "filename": str(filename.root),
            "location": {"column": 1, "row": 1},
            "message": RuffMessage.fake().root,
        }
        return LinterOutput(json.dumps([entry]))


def test_a_violation_parses_to_its_source_line_and_rule() -> None:
    filename = "/Users/me/project/src/a.py"
    row = 3
    rule = "F401"
    output = LinterOutput(
        json.dumps(
            [
                {
                    "code": rule,
                    "filename": filename,
                    "location": {"column": 8, "row": row},
                    "message": "`os` imported but unused",
                    "name": "unused-import",
                }
            ]
        )
    )
    expected = LocatedViolation(
        source=SourcePath(Path(filename)),
        line=LineNumber(row),
        rule=RuleName(rule),
        reported_as=LinterLine("/Users/me/project/src/a.py:3:8: F401 `os` imported but unused"),
    )
    assert RuffJsonParser.parse(output).unwrap().root == (expected,)


def test_a_path_outside_the_working_directory_is_kept_as_reported() -> None:
    filename = SourcePath(Path("/elsewhere/a.py"))
    output = RuffJson.output(filename, RuleName.fake())
    violation = RuffJsonParser.parse(output).unwrap().root[0]
    assert isinstance(violation, LocatedViolation)
    assert violation.source == filename


def test_an_empty_list_holds_no_violations() -> None:
    assert RuffJsonParser.parse(LinterOutput("[]")).unwrap().root == ()


def test_invalid_json_is_a_parse_error() -> None:
    result = RuffJsonParser.parse(LinterOutput("a.py:1:8: F401 `os` imported but unused"))
    assert isinstance(result, Err)
    assert isinstance(result.error, UnparsableOutputError)


def test_json_without_a_rule_code_is_a_parse_error() -> None:
    output = RuffJson.output(SourcePath.fake(), None)
    assert isinstance(RuffJsonParser.parse(output), Err)
