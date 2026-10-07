from enum import StrEnum
from typing import TYPE_CHECKING

from hemolint.b_core.d_domain_model.fixit import FixitParser
from hemolint.b_core.d_domain_model.pyrefly import PyreflyParser
from hemolint.b_core.d_domain_model.ruff_json import RuffJsonParser
from hemolint.b_core.d_domain_model.tach import TachParser
from hemolint.b_core.d_domain_model.violation import LinterName

if TYPE_CHECKING:
    from safe_result import Result

    from hemolint.b_core.d_domain_model.linter_output import (
        LinterOutput,
        ReportedViolations,
        UnparsableOutputError,
    )


# Adding a linter means adding a member, its linter name, and its parser.
class LinterFormat(StrEnum):
    fixit = "fixit"
    pyrefly = "pyrefly"
    ruff_json = "ruff-json"
    tach = "tach"

    # Names the baseline files, so it is the linter, not the format it was read in.
    def linter_name(self) -> LinterName:
        match self:
            case LinterFormat.fixit:
                return LinterName("fixit")
            case LinterFormat.pyrefly:
                return LinterName("pyrefly")
            case LinterFormat.ruff_json:
                return LinterName("ruff")
            case LinterFormat.tach:
                return LinterName("tach")

    def parse(self, output: LinterOutput) -> Result[ReportedViolations, UnparsableOutputError]:
        match self:
            case LinterFormat.fixit:
                return FixitParser.parse(output)
            case LinterFormat.pyrefly:
                return PyreflyParser.parse(output)
            case LinterFormat.ruff_json:
                return RuffJsonParser.parse(output)
            case LinterFormat.tach:
                return TachParser.parse(output)
