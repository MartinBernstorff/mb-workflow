import json
from enum import StrEnum

from pydantic import ConfigDict, Field, JsonValue, TypeAdapter, ValidationError
from safe_result import Err, Ok, Result

from hemolint.b_core.d_domain_model.linter_output import (
    LinterOutput,
    ReportedViolations,
    UnparsableOutputError,
)
from hemolint.b_core.d_domain_model.violation import (
    Fingerprint,
    GlobalViolation,
    LineNumber,
    LinterLine,
    LocatedViolation,
    RuleName,
    SourcePath,
)
from hemolint.d_lib.models import Model, Value


class TachSeverity(StrEnum):
    error = "Error"
    warning = "Warning"


# Code diagnostics are violations; configuration diagnostics mean tach could not check everything.
class TachCategory(StrEnum):
    code = "Code"
    configuration = "Configuration"


class TachErrorMessage(Value[str]):
    @staticmethod
    def fake() -> TachErrorMessage:
        return TachErrorMessage("Circular dependency")


# Tach's JSON holds more fields than hemolint reads, so the rest are ignored.
class _TachModel(Model):
    model_config = ConfigDict(extra="ignore", frozen=True)


# One kind under one category, e.g. `{"Code": {"UndeclaredDependency": {...}}}`.
class _TachDetails(Value[dict[TachCategory, dict[RuleName, JsonValue]]]):
    def code_kind(self) -> Result[tuple[RuleName, JsonValue], UnparsableOutputError]:
        code = self.root.get(TachCategory.code)
        if len(self.root) != 1 or code is None or len(code) != 1:
            # RuleName keys dump as their repr, so the keys are unwrapped first.
            details = {
                category.value: {kind.root: payload for kind, payload in kinds.items()}
                for category, kinds in self.root.items()
            }
            return Err(
                UnparsableOutputError(f"tach could not check everything: {json.dumps(details)}")
            )
        [(kind, payload)] = code.items()
        return Ok((kind, payload))


class _TachGlobal(_TachModel):
    severity: TachSeverity
    details: _TachDetails


class _TachLocated(_TachGlobal):
    file_path: SourcePath
    line_number: LineNumber


class _TachLocatedEntry(Model):
    located: _TachLocated = Field(alias="Located")


class _TachGlobalEntry(Model):
    global_: _TachGlobal = Field(alias="Global")


# Tach reports a failure that stops the whole check, e.g. a circular dependency, as one object.
class _TachError(_TachModel):
    error: TachErrorMessage


class TachParser:
    _OUTPUT = TypeAdapter(tuple[_TachLocatedEntry | _TachGlobalEntry, ...])
    _ERROR = TypeAdapter(_TachError)

    # Keeps tach's paths, which are relative to the tach project root.
    @staticmethod
    def parse(output: LinterOutput) -> Result[ReportedViolations, UnparsableOutputError]:
        try:
            entries = TachParser._OUTPUT.validate_json(output.root)
        except ValidationError as error:
            return Err(TachParser._failure(output, error))
        violations: list[LocatedViolation | GlobalViolation] = []
        for entry in entries:
            violation = TachParser._violation(entry)
            if isinstance(violation, Err):
                return violation
            violations.append(violation.value)
        return Ok(ReportedViolations(tuple(violations)))

    @staticmethod
    def _violation(
        entry: _TachLocatedEntry | _TachGlobalEntry,
    ) -> Result[LocatedViolation | GlobalViolation, UnparsableOutputError]:
        match entry:
            case _TachLocatedEntry(located=located):
                kind = located.details.code_kind()
                if isinstance(kind, Err):
                    return kind
                rule, payload = kind.value
                return Ok(
                    LocatedViolation(
                        source=located.file_path,
                        line=located.line_number,
                        rule=rule,
                        reported_as=LinterLine(
                            f"{located.file_path.root}:{located.line_number.root}: "
                            f"{rule.root} {TachParser._fingerprint(payload).root}"
                        ),
                    )
                )
            case _TachGlobalEntry(global_=global_):
                kind = global_.details.code_kind()
                if isinstance(kind, Err):
                    return kind
                rule, payload = kind.value
                fingerprint = TachParser._fingerprint(payload)
                return Ok(
                    GlobalViolation(
                        rule=rule,
                        fingerprint=fingerprint,
                        reported_as=LinterLine(f"{rule.root} {fingerprint.root}"),
                    )
                )

    # Sorted keys, so tach reordering a payload does not change its fingerprint.
    @staticmethod
    def _fingerprint(payload: JsonValue) -> Fingerprint:
        return Fingerprint(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        )

    @staticmethod
    def _failure(output: LinterOutput, error: ValidationError) -> UnparsableOutputError:
        try:
            failure = TachParser._ERROR.validate_json(output.root)
        except ValidationError:
            return UnparsableOutputError(f"Not tach JSON output: {error}")
        return UnparsableOutputError(f"tach failed: {failure.error.root}: {output.root}")
