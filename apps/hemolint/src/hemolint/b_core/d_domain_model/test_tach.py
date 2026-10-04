import json
from pathlib import Path
from typing import TYPE_CHECKING

from safe_result import Err

from hemolint.b_core.d_domain_model.linter_output import LinterOutput, UnparsableOutputError
from hemolint.b_core.d_domain_model.tach import TachCategory, TachParser, TachSeverity
from hemolint.b_core.d_domain_model.violation import (
    GlobalViolation,
    LineNumber,
    LocatedViolation,
    RuleName,
    SourcePath,
)

if TYPE_CHECKING:
    from pydantic import JsonValue


class TachJson:
    # One diagnostic in `tach check --output json`, without the fields hemolint ignores.
    @staticmethod
    def located(
        severity: TachSeverity, category: TachCategory, kind: RuleName, payload: JsonValue
    ) -> LinterOutput:
        return LinterOutput(
            json.dumps(
                [
                    {
                        "Located": {
                            "file_path": "src/a/mod.py",
                            "line_number": 3,
                            "severity": severity.value,
                            "details": {category.value: {kind.root: payload}},
                        }
                    }
                ]
            )
        )

    @staticmethod
    def global_(category: TachCategory, kind: RuleName, payload: JsonValue) -> LinterOutput:
        details = {category.value: {kind.root: payload}}
        return LinterOutput(json.dumps([{"Global": {"severity": "Error", "details": details}}]))


dependency: dict[str, JsonValue] = {
    "dependency": "b.x",
    "usage_module": "a",
    "definition_module": "b",
}


def test_a_located_code_error_parses_to_its_source_line_and_kind() -> None:
    kind = RuleName("UndeclaredDependency")
    output = TachJson.located(TachSeverity.error, TachCategory.code, kind, dependency)
    violation = TachParser.parse(output).unwrap().root[0]
    assert isinstance(violation, LocatedViolation)
    assert (violation.source, violation.line, violation.rule) == (
        SourcePath(Path("src/a/mod.py")),
        LineNumber(3),
        kind,
    )


def test_a_located_code_warning_is_a_violation_too() -> None:
    kind = RuleName("UnusedIgnoreDirective")
    output = TachJson.located(TachSeverity.warning, TachCategory.code, kind, [])
    assert TachParser.parse(output).unwrap().root[0].rule == kind


def test_a_global_code_diagnostic_parses_to_its_kind_without_a_source() -> None:
    kind = RuleName("UnusedDependencies")
    output = TachJson.global_(TachCategory.code, kind, dependency)
    violation = TachParser.parse(output).unwrap().root[0]
    assert isinstance(violation, GlobalViolation)
    assert violation.rule == kind


def test_a_reordered_global_payload_has_the_same_fingerprint() -> None:
    reordered: JsonValue = dict(reversed(dependency.items()))
    original = (
        TachParser.parse(TachJson.global_(TachCategory.code, RuleName.fake(), dependency))
        .unwrap()
        .root[0]
    )
    swapped = (
        TachParser.parse(TachJson.global_(TachCategory.code, RuleName.fake(), reordered))
        .unwrap()
        .root[0]
    )
    assert isinstance(original, GlobalViolation)
    assert isinstance(swapped, GlobalViolation)
    assert original.fingerprint == swapped.fingerprint


def test_another_global_payload_has_another_fingerprint() -> None:
    other: JsonValue = {**dependency, "dependency": "b.y"}
    first = (
        TachParser.parse(TachJson.global_(TachCategory.code, RuleName.fake(), dependency))
        .unwrap()
        .root[0]
    )
    second = (
        TachParser.parse(TachJson.global_(TachCategory.code, RuleName.fake(), other))
        .unwrap()
        .root[0]
    )
    assert isinstance(first, GlobalViolation)
    assert isinstance(second, GlobalViolation)
    assert first.fingerprint != second.fingerprint


def test_an_empty_list_holds_no_violations() -> None:
    assert TachParser.parse(LinterOutput("[]")).unwrap().root == ()


def test_a_located_configuration_diagnostic_is_a_parse_error() -> None:
    output = TachJson.located(
        TachSeverity.error, TachCategory.configuration, RuleName("ModuleConfigNotFound"), []
    )
    result = TachParser.parse(output)
    assert isinstance(result, Err)
    assert isinstance(result.error, UnparsableOutputError)


def test_a_global_configuration_diagnostic_is_a_parse_error() -> None:
    output = TachJson.global_(
        TachCategory.configuration, RuleName("ModuleNotFound"), {"file_mod_path": "c"}
    )
    assert isinstance(TachParser.parse(output), Err)


def test_a_skipped_file_is_a_parse_error() -> None:
    skipped = RuleName("SkippedFileSyntaxError")
    output = TachJson.global_(TachCategory.configuration, skipped, {"file_path": "a/bad.py"})
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
