import json
from pathlib import Path

from safe_result import Err

from hemolint.b_core.d_domain_model.linter_output import LinterOutput, UnparsableOutputError
from hemolint.b_core.d_domain_model.pyrefly import PyreflyMessage, PyreflyParser, PyreflySeverity
from hemolint.b_core.d_domain_model.violation import (
    LineNumber,
    LinterLine,
    LocatedViolation,
    RuleName,
    SourcePath,
)


class PyreflyJson:
    # `pyrefly check --output-format json` with one error, without the fields hemolint ignores.
    @staticmethod
    def output(
        path: SourcePath, stop_line: LineNumber, severity: PyreflySeverity, rule: RuleName | None
    ) -> LinterOutput:
        entry = {
            "line": 1,
            "column": 10,
            "stop_line": stop_line.root,
            "stop_column": 13,
            "path": str(path.root),
            "name": None if rule is None else rule.root,
            "concise_description": PyreflyMessage.fake().root,
            "severity": severity.value,
        }
        return LinterOutput(json.dumps({"errors": [entry]}))

    @staticmethod
    def reported_as(stop_line: LineNumber, severity: PyreflySeverity) -> LinterLine:
        output = PyreflyJson.output(SourcePath.fake(), stop_line, severity, RuleName.fake())
        violation = PyreflyParser.parse(output).unwrap().root[0]
        assert isinstance(violation, LocatedViolation)
        return violation.reported_as


def test_an_error_parses_to_its_source_line_and_rule() -> None:
    path = "src/a.py"
    line = 3
    rule = "bad-assignment"
    output = LinterOutput(
        json.dumps(
            {
                "errors": [
                    {
                        "line": line,
                        "column": 10,
                        "stop_line": line,
                        "stop_column": 13,
                        "path": path,
                        "code": -2,
                        "name": rule,
                        "description": "`Literal['a']` is not assignable to `int`",
                        "concise_description": "`Literal['a']` is not assignable to `int`",
                        "severity": "error",
                    }
                ]
            }
        )
    )
    expected = LocatedViolation(
        source=SourcePath(Path(path)),
        line=LineNumber(line),
        rule=RuleName(rule),
        reported_as=LinterLine(
            "ERROR src/a.py:3:10-13: `Literal['a']` is not assignable to `int` [bad-assignment]"
        ),
    )
    assert PyreflyParser.parse(output).unwrap().root == (expected,)


def test_an_error_spanning_lines_prints_its_stop_line() -> None:
    reported_as = PyreflyJson.reported_as(LineNumber(2), PyreflySeverity.error)
    assert ":1:10-2:13: " in reported_as.root


def test_a_warning_is_a_violation_printed_as_a_warning() -> None:
    reported_as = PyreflyJson.reported_as(LineNumber(1), PyreflySeverity.warn)
    assert reported_as.root.startswith(" WARN ")


def test_no_errors_hold_no_violations() -> None:
    assert PyreflyParser.parse(LinterOutput('{"errors": []}')).unwrap().root == ()


def test_invalid_json_is_a_parse_error() -> None:
    result = PyreflyParser.parse(LinterOutput("Path `a.py` does not exist"))
    assert isinstance(result, Err)
    assert isinstance(result.error, UnparsableOutputError)


def test_empty_output_is_a_parse_error() -> None:
    assert isinstance(PyreflyParser.parse(LinterOutput("")), Err)


def test_json_without_a_rule_name_is_a_parse_error() -> None:
    output = PyreflyJson.output(SourcePath.fake(), LineNumber(1), PyreflySeverity.error, None)
    assert isinstance(PyreflyParser.parse(output), Err)
