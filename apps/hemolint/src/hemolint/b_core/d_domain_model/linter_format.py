from enum import StrEnum
from typing import TYPE_CHECKING

from hemolint.b_core.d_domain_model.fixit import FixitParser
from hemolint.b_core.d_domain_model.violation import LinterName

if TYPE_CHECKING:
    from safe_result import Result

    from hemolint.b_core.d_domain_model.linter_output import (
        LinterOutput,
        ReportedViolations,
        UnparsableLineError,
    )


# Adding a linter means adding a member and its parser.
class LinterFormat(StrEnum):
    fixit = "fixit"

    def linter_name(self) -> LinterName:
        return LinterName(self.value)

    def parse(self, output: LinterOutput) -> Result[ReportedViolations, UnparsableLineError]:
        match self:
            case LinterFormat.fixit:
                return FixitParser.parse(output)
