import re
from pathlib import Path

from safe_result import Err, Ok, Result

from hemolint.b_core.d_domain_model.linter_output import (
    LinterOutput,
    ReportedViolations,
    UnparsableOutputError,
)
from hemolint.b_core.d_domain_model.violation import (
    LineNumber,
    LinterLine,
    ReportedViolation,
    RuleName,
    SourcePath,
)


class FixitParser:
    # `<path>@<line>:<column> <rule>: <message>`. The greedy path allows an @ inside it, but no
    # ": ", so an EXCEPTION line whose message looks like a violation is still rejected.
    _VIOLATION = re.compile(r"(?P<path>(?:(?!: ).)+)@(?P<line>\d+):\d+ (?P<rule>\w+): .*")

    @staticmethod
    def parse(output: LinterOutput) -> Result[ReportedViolations, UnparsableOutputError]:
        violations: list[ReportedViolation] = []
        for line in output.root.splitlines():
            if not line.strip():
                continue
            match = FixitParser._VIOLATION.fullmatch(line)
            if match is None:
                return Err(UnparsableOutputError(f"Not a Fixit violation: {line}"))
            violations.append(
                ReportedViolation(
                    source=SourcePath(Path(match["path"])),
                    line=LineNumber(int(match["line"])),
                    rule=RuleName(match["rule"]),
                    reported_as=LinterLine(line),
                )
            )
        return Ok(ReportedViolations(tuple(violations)))
