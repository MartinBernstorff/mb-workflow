from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError
from safe_result import Err, Ok, Result

from hemolint.b_core.d_domain_model.linter_output import (
    LinterOutput,
    ReportedViolations,
    UnparsableLineError,
)
from hemolint.b_core.d_domain_model.violation import (
    LineNumber,
    LinterLine,
    ReportedViolation,
    RuleName,
    SourcePath,
)
from hemolint.d_lib.models import Value


class ColumnNumber(Value[int]):
    @staticmethod
    def fake() -> ColumnNumber:
        return ColumnNumber(1)


class RuffMessage(Value[str]):
    @staticmethod
    def fake() -> RuffMessage:
        return RuffMessage("`os` imported but unused")


# Ruff's JSON holds more fields than hemolint reads, so the rest are ignored.
class _RuffModel(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class _RuffLocation(_RuffModel):
    row: LineNumber
    column: ColumnNumber


class _RuffViolation(_RuffModel):
    code: RuleName
    filename: SourcePath
    location: _RuffLocation
    message: RuffMessage

    # Ruff's concise output format, so a new violation prints the way ruff would print it.
    def reported_as(self) -> LinterLine:
        return LinterLine(
            f"{self.filename.root}:{self.location.row.root}:{self.location.column.root}: "
            f"{self.code.root} {self.message.root}"
        )


class RuffJsonParser:
    _OUTPUT = TypeAdapter(tuple[_RuffViolation, ...])

    # Ruff reports absolute paths; finding the violations makes them relative.
    @staticmethod
    def parse(output: LinterOutput) -> Result[ReportedViolations, UnparsableLineError]:
        try:
            entries = RuffJsonParser._OUTPUT.validate_json(output.root)
        except ValidationError as error:
            return Err(UnparsableLineError(f"Not ruff JSON output: {error}"))
        return Ok(
            ReportedViolations(
                tuple(
                    ReportedViolation(
                        source=entry.filename,
                        line=entry.location.row,
                        rule=entry.code,
                        reported_as=entry.reported_as(),
                    )
                    for entry in entries
                )
            )
        )
