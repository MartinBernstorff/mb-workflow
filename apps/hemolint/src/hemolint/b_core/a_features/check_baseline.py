from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from hemolint.b_core.a_features.find_violations import ViolationFinder
from hemolint.b_core.d_domain_model.drift import Drift

if TYPE_CHECKING:
    from hemolint.b_core.c_secondary_ports.baseline_store import (
        BaselineStore,
        BaselineStoreError,
    )
    from hemolint.b_core.c_secondary_ports.source_lines import SourceLines
    from hemolint.b_core.d_domain_model.linter_format import LinterFormat
    from hemolint.b_core.d_domain_model.linter_output import LinterOutput, UnparsableOutputError
    from hemolint.b_core.d_domain_model.violation import (
        MissingSourceLineError,
        OutsideWorkingDirectoryError,
        WorkingDirectory,
    )


class BaselineCheck:
    @staticmethod
    def check(
        output: LinterOutput,
        linter_format: LinterFormat,
        directory: WorkingDirectory,
        lines: SourceLines,
        store: BaselineStore,
    ) -> Result[
        Drift,
        UnparsableOutputError
        | OutsideWorkingDirectoryError
        | MissingSourceLineError
        | BaselineStoreError,
    ]:
        found = ViolationFinder.find(output, linter_format, directory, lines)
        if isinstance(found, Err):
            return found
        baseline = store.read()
        if isinstance(baseline, Err):
            return baseline
        return Ok(Drift.between(baseline.value, found.value))
