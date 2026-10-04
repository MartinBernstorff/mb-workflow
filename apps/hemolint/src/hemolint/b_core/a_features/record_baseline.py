from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from hemolint.b_core.d_domain_model.baseline import Baseline, BaselineFile, Violation
from hemolint.b_core.d_domain_model.violation import Fingerprint

if TYPE_CHECKING:
    from hemolint.b_core.c_secondary_ports.baseline_store import (
        BaselineStore,
        BaselineStoreError,
    )
    from hemolint.b_core.c_secondary_ports.source_lines import SourceLines
    from hemolint.b_core.d_domain_model.baseline import BaselineChange
    from hemolint.b_core.d_domain_model.linter_format import LinterFormat
    from hemolint.b_core.d_domain_model.linter_output import LinterOutput, UnparsableLineError
    from hemolint.b_core.d_domain_model.violation import (
        MissingSourceLineError,
        OutsideWorkingDirectoryError,
        WorkingDirectory,
    )


class BaselineRecording:
    # Writes the exact current state: new violations are added, fixed ones removed.
    @staticmethod
    def record(
        output: LinterOutput,
        linter_format: LinterFormat,
        directory: WorkingDirectory,
        lines: SourceLines,
        store: BaselineStore,
    ) -> Result[
        BaselineChange,
        UnparsableLineError
        | OutsideWorkingDirectoryError
        | MissingSourceLineError
        | BaselineStoreError,
    ]:
        reported = linter_format.parse(output)
        if isinstance(reported, Err):
            return reported
        violations: list[Violation] = []
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
            violations.append(Violation(file=file, fingerprint=Fingerprint.of(line.value)))
        current = Baseline.of(violations)
        previous = store.read()
        if isinstance(previous, Err):
            return previous
        written = store.write(current)
        if isinstance(written, Err):
            return written
        return Ok(current.change_from(previous.value))
