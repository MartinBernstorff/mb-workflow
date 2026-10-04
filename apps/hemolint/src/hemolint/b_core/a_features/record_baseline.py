from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from hemolint.b_core.a_features.find_violations import ViolationFinder
from hemolint.b_core.d_domain_model.baseline import Baseline

if TYPE_CHECKING:
    from hemolint.b_core.c_secondary_ports.baseline_store import (
        BaselineStore,
        BaselineStoreError,
    )
    from hemolint.b_core.c_secondary_ports.source_lines import SourceLines
    from hemolint.b_core.d_domain_model.baseline import BaselineChange
    from hemolint.b_core.d_domain_model.linter_format import LinterFormat
    from hemolint.b_core.d_domain_model.linter_output import LinterOutput, UnparsableOutputError
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
        UnparsableOutputError
        | OutsideWorkingDirectoryError
        | MissingSourceLineError
        | BaselineStoreError,
    ]:
        found = ViolationFinder.find(output, linter_format, directory, lines)
        if isinstance(found, Err):
            return found
        current = Baseline.of(reported.violation for reported in found.value)
        previous = store.read()
        if isinstance(previous, Err):
            return previous
        written = store.write(current)
        if isinstance(written, Err):
            return written
        return Ok(current.change_from(previous.value))
