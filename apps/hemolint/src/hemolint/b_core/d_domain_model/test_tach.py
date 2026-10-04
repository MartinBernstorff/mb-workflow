import json
from pathlib import Path
from typing import TYPE_CHECKING

from safe_result import Err

from hemolint.b_core.d_domain_model.linter_output import LinterOutput, UnparsableOutputError
from hemolint.b_core.d_domain_model.tach import TachCategory, TachParser, TachSeverity
from hemolint.b_core.d_domain_model.violation import (
    Fingerprint,
    GlobalViolation,
    LineNumber,
    LinterLine,
    LocatedViolation,
    RuleName,
    SourcePath,
)

if TYPE_CHECKING:
    from pydantic import JsonValue


class TachJson:
    @staticmethod
    def located(
        at: LocatedViolation, severity: TachSeverity, category: TachCategory, payload: JsonValue
    ) -> LinterOutput:
        return LinterOutput(
            json.dumps(
                [
                    {
                        "Located": {
                            "file_path": str(at.source.root),
                            "line_number": at.line.root,
                            "severity": severity.value,
                            "details": {category.value: {at.rule.root: payload}},
                        }
                    }
                ]
            )
        )

    @staticmethod
    def global_(
        severity: TachSeverity, category: TachCategory, kind: RuleName, payload: JsonValue
    ) -> LinterOutput:
        details = {category.value: {kind.root: payload}}
        return LinterOutput(
            json.dumps([{"Global": {"severity": severity.value, "details": details}}])
        )

    @staticmethod
    def global_fingerprint(payload: JsonValue) -> Fingerprint:
        output = TachJson.global_(TachSeverity.error, TachCategory.code, RuleName.fake(), payload)
        violation = TachParser.parse(output).unwrap().root[0]
        assert isinstance(violation, GlobalViolation)
        return violation.fingerprint


dependency: dict[str, JsonValue] = {
    "dependency": "b.x",
    "usage_module": "a",
    "definition_module": "b",
}


def test_a_located_code_error_parses_to_its_source_line_and_kind() -> None:
    at = LocatedViolation(
        source=SourcePath(Path("src/a/mod.py")),
        line=LineNumber(3),
        rule=RuleName("UndeclaredDependency"),
        reported_as=LinterLine.fake(),
    )
    output = TachJson.located(at, TachSeverity.error, TachCategory.code, dependency)
    violation = TachParser.parse(output).unwrap().root[0]
    assert isinstance(violation, LocatedViolation)
    assert (violation.source, violation.line, violation.rule) == (at.source, at.line, at.rule)


def test_a_located_code_warning_is_a_violation_too() -> None:
    at = LocatedViolation.fake().model_copy(update={"rule": RuleName("UnusedIgnoreDirective")})
    output = TachJson.located(at, TachSeverity.warning, TachCategory.code, [])
    assert TachParser.parse(output).unwrap().root[0].rule == at.rule


def test_a_global_code_diagnostic_parses_to_its_kind_without_a_source() -> None:
    kind = RuleName("UnusedDependencies")
    output = TachJson.global_(TachSeverity.error, TachCategory.code, kind, dependency)
    violation = TachParser.parse(output).unwrap().root[0]
    assert isinstance(violation, GlobalViolation)
    assert violation.rule == kind


def test_a_global_code_warning_is_a_violation_too() -> None:
    kind = RuleName("UnusedDependencies")
    output = TachJson.global_(TachSeverity.warning, TachCategory.code, kind, dependency)
    assert TachParser.parse(output).unwrap().root[0].rule == kind


def test_a_reordered_global_payload_has_the_same_fingerprint() -> None:
    reordered: JsonValue = dict(reversed(dependency.items()))
    assert TachJson.global_fingerprint(dependency) == TachJson.global_fingerprint(reordered)


def test_another_global_payload_has_another_fingerprint() -> None:
    other: JsonValue = {**dependency, "dependency": "b.y"}
    assert TachJson.global_fingerprint(dependency) != TachJson.global_fingerprint(other)


def test_an_empty_list_holds_no_violations() -> None:
    assert TachParser.parse(LinterOutput("[]")).unwrap().root == ()


def test_a_located_configuration_diagnostic_is_a_parse_error() -> None:
    at = LocatedViolation.fake().model_copy(update={"rule": RuleName("ModuleConfigNotFound")})
    output = TachJson.located(at, TachSeverity.error, TachCategory.configuration, [])
    result = TachParser.parse(output)
    assert isinstance(result, Err)
    assert isinstance(result.error, UnparsableOutputError)


def test_a_global_configuration_diagnostic_is_a_parse_error() -> None:
    output = TachJson.global_(
        TachSeverity.error,
        TachCategory.configuration,
        RuleName("ModuleNotFound"),
        {"file_mod_path": "c"},
    )
    assert isinstance(TachParser.parse(output), Err)


def test_a_skipped_file_is_a_parse_error() -> None:
    skipped = RuleName("SkippedFileSyntaxError")
    output = TachJson.global_(
        TachSeverity.error, TachCategory.configuration, skipped, {"file_path": "a/bad.py"}
    )
    result = TachParser.parse(output)
    assert isinstance(result, Err)
    assert f'"{skipped.root}"' in str(result.error)


def test_a_tach_error_is_a_parse_error_naming_it() -> None:
    error = "Circular dependency"
    output = LinterOutput(json.dumps({"error": error, "dependencies": ["a", "b"]}))
    result = TachParser.parse(output)
    assert isinstance(result, Err)
    assert error in str(result.error)


def test_invalid_json_is_a_parse_error() -> None:
    assert isinstance(TachParser.parse(LinterOutput("Configuration file not found.")), Err)


def test_empty_output_is_a_parse_error() -> None:
    assert isinstance(TachParser.parse(LinterOutput("")), Err)
