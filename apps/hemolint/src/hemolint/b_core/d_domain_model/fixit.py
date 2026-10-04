import re
from pathlib import Path

from safe_result import Err, Ok, Result

from hemolint.b_core.d_domain_model.linter_output import (
    LinterOutput,
    ReportedViolations,
    UnparsableLineError,
)
from hemolint.b_core.d_domain_model.violation import (
    LineNumber,
    ReportedViolation,
    RuleName,
    SourcePath,
)


class FixitParser:
    # `<path>@<line>:<column> <rule>: <message>`; the greedy path allows an @ inside it.
    _VIOLATION = re.compile(r"(?P<path>.+)@(?P<line>\d+):\d+ (?P<rule>\w+): .*")

    @staticmethod
    def parse(output: LinterOutput) -> Result[ReportedViolations, UnparsableLineError]:
        violations: list[ReportedViolation] = []
        for line in output.root.splitlines():
            if not line.strip():
                continue
            match = FixitParser._VIOLATION.fullmatch(line)
            if match is None:
                return Err(UnparsableLineError(f"Not a Fixit violation: {line}"))
            violations.append(
                ReportedViolation(
                    source=SourcePath(Path(match["path"])),
                    line=LineNumber(int(match["line"])),
                    rule=RuleName(match["rule"]),
                )
            )
        return Ok(ReportedViolations(tuple(violations)))
