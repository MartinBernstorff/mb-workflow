from enum import StrEnum
from typing import TYPE_CHECKING

from hemolint.b_core.d_domain_model.fixit import FixitParser
from hemolint.b_core.d_domain_model.ruff_json import RuffJsonParser
from hemolint.b_core.d_domain_model.violation import LinterName

if TYPE_CHECKING:
    from safe_result import Result

    from hemolint.b_core.d_domain_model.linter_output import (
        LinterOutput,
        ReportedViolations,
        UnparsableLineError,
    )


# Adding a linter means adding a member, its linter name, and its parser.
class LinterFormat(StrEnum):
    fixit = "fixit"
    ruff_json = "ruff-json"

    # Names the baseline files, so it is the linter, not the format it was read in.
    def linter_name(self) -> LinterName:
        match self:
            case LinterFormat.fixit:
                return LinterName("fixit")
            case LinterFormat.ruff_json:
                return LinterName("ruff")

    def parse(self, output: LinterOutput) -> Result[ReportedViolations, UnparsableLineError]:
        match self:
            case LinterFormat.fixit:
                return FixitParser.parse(output)
            case LinterFormat.ruff_json:
                return RuffJsonParser.parse(output)
