from enum import StrEnum

from pydantic import ConfigDict, TypeAdapter, ValidationError
from safe_result import Err, Ok, Result

from hemolint.b_core.d_domain_model.linter_output import (
    LinterOutput,
    ReportedViolations,
    UnparsableOutputError,
)
from hemolint.b_core.d_domain_model.violation import (
    ColumnNumber,
    LineNumber,
    LinterLine,
    LocatedViolation,
    RuleName,
    SourcePath,
)
from hemolint.d_lib.models import Model, Value


# Every severity is a violation; `--min-severity` decides which ones pyrefly reports.
class PyreflySeverity(StrEnum):
    error = "error"
    warn = "warn"
    info = "info"
    ignore = "ignore"


class PyreflyMessage(Value[str]):
    @staticmethod
    def fake() -> PyreflyMessage:
        return PyreflyMessage("`Literal['a']` is not assignable to `int`")


# Pyrefly's JSON holds more fields than hemolint reads, so the rest are ignored.
class _PyreflyModel(Model):
    model_config = ConfigDict(extra="ignore", frozen=True)


class _PyreflyError(_PyreflyModel):
    path: SourcePath
    line: LineNumber
    column: ColumnNumber
    stop_line: LineNumber
    stop_column: ColumnNumber
    name: RuleName
    concise_description: PyreflyMessage
    severity: PyreflySeverity

    # Pyrefly's min-text output format, so a new violation prints the way pyrefly would print it.
    def to_linter_line(self) -> LinterLine:
        stop = (
            f"{self.stop_column.root}"
            if self.stop_line == self.line
            else f"{self.stop_line.root}:{self.stop_column.root}"
        )
        return LinterLine(
            f"{self.severity.value.upper():>5} "
            f"{self.path.root}:{self.line.root}:{self.column.root}-{stop}: "
            f"{self.concise_description.root} [{self.name.root}]"
        )


class _PyreflyOutput(_PyreflyModel):
    errors: tuple[_PyreflyError, ...]


class PyreflyParser:
    _OUTPUT = TypeAdapter(_PyreflyOutput)

    # Keeps pyrefly's paths, which are relative to the directory it ran in.
    @staticmethod
    def parse(output: LinterOutput) -> Result[ReportedViolations, UnparsableOutputError]:
        try:
            parsed = PyreflyParser._OUTPUT.validate_json(output.root)
        except ValidationError as error:
            return Err(UnparsableOutputError(f"Not pyrefly JSON output: {error}"))
        return Ok(
            ReportedViolations(
                tuple(
                    LocatedViolation(
                        source=entry.path,
                        line=entry.line,
                        rule=entry.name,
                        reported_as=entry.to_linter_line(),
                    )
                    for entry in parsed.errors
                )
            )
        )
