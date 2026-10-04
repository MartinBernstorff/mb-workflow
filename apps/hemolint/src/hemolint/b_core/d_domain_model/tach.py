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
        if TachCategory.configuration in self.root:
            return Err(
                UnparsableOutputError(f"tach could not check everything: {self._as_output().root}")
            )
        code = self.root.get(TachCategory.code)
        if len(self.root) != 1 or code is None or len(code) != 1:
            return Err(
                UnparsableOutputError(f"Not one tach diagnostic kind: {self._as_output().root}")
            )
        [(kind, payload)] = code.items()
        return Ok((kind, payload))

    # The details as tach printed them. RuleName keys dump as their repr, so they are unwrapped.
    def _as_output(self) -> LinterOutput:
        return LinterOutput(
            json.dumps(
                {
                    category.value: {kind.root: payload for kind, payload in kinds.items()}
                    for category, kinds in self.root.items()
                }
            )
        )


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
            return Err(TachParser._unparsable_error(output, error))
        violations: list[LocatedViolation | GlobalViolation] = []
        for entry in entries:
            violation = TachParser._parse_entry(entry)
            if isinstance(violation, Err):
                return violation
            violations.append(violation.value)
        return Ok(ReportedViolations(tuple(violations)))

    @staticmethod
    def _parse_entry(
        entry: _TachLocatedEntry | _TachGlobalEntry,
    ) -> Result[LocatedViolation | GlobalViolation, UnparsableOutputError]:
        diagnostic = entry.located if isinstance(entry, _TachLocatedEntry) else entry.global_
        code_kind = diagnostic.details.code_kind()
        if isinstance(code_kind, Err):
            return code_kind
        rule, payload = code_kind.value
        # Fingerprints a global violation; a located one is fingerprinted by its source line later.
        fingerprint = TachParser._fingerprint_of(payload)
        if isinstance(diagnostic, _TachLocated):
            return Ok(
                LocatedViolation(
                    source=diagnostic.file_path,
                    line=diagnostic.line_number,
                    rule=rule,
                    reported_as=LinterLine(
                        f"{diagnostic.file_path.root}:{diagnostic.line_number.root}: "
                        f"{rule.root} {fingerprint.root}"
                    ),
                )
            )
        return Ok(
            GlobalViolation(
                rule=rule,
                fingerprint=fingerprint,
                reported_as=LinterLine(f"{rule.root} {fingerprint.root}"),
            )
        )

    # Sorted keys, so tach reordering a payload does not change its fingerprint.
    @staticmethod
    def _fingerprint_of(payload: JsonValue) -> Fingerprint:
        return Fingerprint(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        )

    @staticmethod
    def _unparsable_error(output: LinterOutput, error: ValidationError) -> UnparsableOutputError:
        try:
            failure = TachParser._ERROR.validate_json(output.root)
        except ValidationError:
            return UnparsableOutputError(f"Not tach JSON output: {error}")
        return UnparsableOutputError(f"tach failed: {failure.error.root}: {output.root}")
