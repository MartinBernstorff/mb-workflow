import sys
from typing import TYPE_CHECKING

from safe_result import Err, Ok

from hemolint.b_core.a_features.record_baseline import BaselineRecording
from hemolint.b_core.d_domain_model.linter_output import UnparsableLineError
from hemolint.c_infrastructure.disk_baseline_store import DiskBaselineStore
from hemolint.c_infrastructure.disk_source_lines import DiskSourceLines
from hemolint.d_lib.models import Value

if TYPE_CHECKING:
    from hemolint.b_core.d_domain_model.baseline import BaselineDirectory
    from hemolint.b_core.d_domain_model.linter_format import LinterFormat
    from hemolint.b_core.d_domain_model.linter_output import LinterOutput
    from hemolint.b_core.d_domain_model.violation import WorkingDirectory


class ExitCode(Value[int]):
    @staticmethod
    def fake() -> ExitCode:
        return ExitCode(0)


class Commands:
    @staticmethod
    def record_baseline(
        output: LinterOutput,
        linter_format: LinterFormat,
        working: WorkingDirectory,
        baseline: BaselineDirectory,
    ) -> ExitCode:
        match BaselineRecording.record(
            output,
            linter_format,
            working,
            DiskSourceLines(working),
            DiskBaselineStore(baseline),
        ):
            case Ok(change):
                _ = sys.stdout.write(
                    f"Added {change.added.root} and removed {change.removed.root} violations.\n"
                )
                return ExitCode(0)
            case Err(UnparsableLineError() as error):
                _ = sys.stderr.write(f"{error}\n")
                return ExitCode(2)
            case Err(error):
                _ = sys.stderr.write(f"{error}\n")
                return ExitCode(1)
