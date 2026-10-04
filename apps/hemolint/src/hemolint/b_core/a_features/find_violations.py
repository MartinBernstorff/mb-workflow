from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from hemolint.b_core.d_domain_model.baseline import BaselineFile, FoundViolation, Violation
from hemolint.b_core.d_domain_model.violation import (
    Fingerprint,
    GlobalViolation,
    LocatedViolation,
    SourcePath,
)

if TYPE_CHECKING:
    from hemolint.b_core.c_secondary_ports.source_lines import SourceLines
    from hemolint.b_core.d_domain_model.linter_format import LinterFormat
    from hemolint.b_core.d_domain_model.linter_output import LinterOutput, UnparsableOutputError
    from hemolint.b_core.d_domain_model.violation import (
        MissingSourceLineError,
        OutsideWorkingDirectoryError,
        WorkingDirectory,
    )


class ViolationFinder:
    @staticmethod
    def find(
        output: LinterOutput,
        linter_format: LinterFormat,
        directory: WorkingDirectory,
        lines: SourceLines,
    ) -> Result[
        tuple[FoundViolation, ...],
        UnparsableOutputError | OutsideWorkingDirectoryError | MissingSourceLineError,
    ]:
        reported = linter_format.parse(output)
        if isinstance(reported, Err):
            return reported
        found: list[FoundViolation] = []
        for violation in reported.value.root:
            match violation:
                case LocatedViolation():
                    placed = ViolationFinder._place_located(violation, directory, lines)
                    if isinstance(placed, Err):
                        return placed
                    source, fingerprint = placed.value
                case GlobalViolation():
                    source, fingerprint = SourcePath.global_diagnostics(), violation.fingerprint
            file = BaselineFile(
                source=source, linter=linter_format.linter_name(), rule=violation.rule
            )
            found.append(
                FoundViolation(
                    violation=Violation(file=file, fingerprint=fingerprint),
                    reported_as=violation.reported_as,
                )
            )
        return Ok(tuple(found))

    @staticmethod
    def _place_located(
        violation: LocatedViolation, directory: WorkingDirectory, lines: SourceLines
    ) -> Result[
        tuple[SourcePath, Fingerprint], OutsideWorkingDirectoryError | MissingSourceLineError
    ]:
        source = violation.source.relative_to_working_directory(directory)
        if isinstance(source, Err):
            return source
        line = lines.read(source.value, violation.line)
        if isinstance(line, Err):
            return line
        return Ok((source.value, Fingerprint.of(line.value)))
