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
    # Fingerprints each reported violation, in output order.
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
                    located = ViolationFinder._located(violation, linter_format, directory, lines)
                    if isinstance(located, Err):
                        return located
                    found.append(located.value)
                case GlobalViolation():
                    found.append(ViolationFinder._global(violation, linter_format))
        return Ok(tuple(found))

    # Fingerprinted by its source line.
    @staticmethod
    def _located(
        violation: LocatedViolation,
        linter_format: LinterFormat,
        directory: WorkingDirectory,
        lines: SourceLines,
    ) -> Result[FoundViolation, OutsideWorkingDirectoryError | MissingSourceLineError]:
        source = violation.source.relative_to_working_directory(directory)
        if isinstance(source, Err):
            return source
        line = lines.read(source.value, violation.line)
        if isinstance(line, Err):
            return line
        file = BaselineFile(
            source=source.value, linter=linter_format.linter_name(), rule=violation.rule
        )
        return Ok(
            FoundViolation(
                violation=Violation(file=file, fingerprint=Fingerprint.of(line.value)),
                reported_as=violation.reported_as,
            )
        )

    # Carries its own fingerprint and is kept under the global source, so no line is read.
    @staticmethod
    def _global(violation: GlobalViolation, linter_format: LinterFormat) -> FoundViolation:
        file = BaselineFile(
            source=SourcePath.global_diagnostics(),
            linter=linter_format.linter_name(),
            rule=violation.rule,
        )
        return FoundViolation(
            violation=Violation(file=file, fingerprint=violation.fingerprint),
            reported_as=violation.reported_as,
        )
