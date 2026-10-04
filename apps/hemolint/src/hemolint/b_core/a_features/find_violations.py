from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from hemolint.b_core.d_domain_model.baseline import BaselineFile, FoundViolation, Violation
from hemolint.b_core.d_domain_model.violation import Fingerprint

if TYPE_CHECKING:
    from hemolint.b_core.c_secondary_ports.source_lines import SourceLines
    from hemolint.b_core.d_domain_model.linter_format import LinterFormat
    from hemolint.b_core.d_domain_model.linter_output import LinterOutput, UnparsableLineError
    from hemolint.b_core.d_domain_model.violation import (
        MissingSourceLineError,
        OutsideWorkingDirectoryError,
        WorkingDirectory,
    )


class ViolationFinder:
    # Fingerprints each reported violation by its source line, in output order.
    @staticmethod
    def find(
        output: LinterOutput,
        linter_format: LinterFormat,
        directory: WorkingDirectory,
        lines: SourceLines,
    ) -> Result[
        tuple[FoundViolation, ...],
        UnparsableLineError | OutsideWorkingDirectoryError | MissingSourceLineError,
    ]:
        reported = linter_format.parse(output)
        if isinstance(reported, Err):
            return reported
        found: list[FoundViolation] = []
        for violation in reported.value.root:
            source = violation.source.relative_to_working_directory(directory)
            if isinstance(source, Err):
                return source
            line = lines.read(source.value, violation.line)
            if isinstance(line, Err):
                return line
            file = BaselineFile(
                source=source.value, linter=linter_format.linter_name(), rule=violation.rule
            )
            found.append(
                FoundViolation(
                    violation=Violation(file=file, fingerprint=Fingerprint.of(line.value)),
                    reported_as=violation.reported_as,
                )
            )
        return Ok(tuple(found))
