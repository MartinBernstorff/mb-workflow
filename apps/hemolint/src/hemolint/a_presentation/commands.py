import sys
from typing import TYPE_CHECKING

from safe_result import Err, Ok

from hemolint.b_core.a_features.check_baseline import BaselineCheck
from hemolint.b_core.a_features.prune_baseline import BaselinePruning
from hemolint.b_core.a_features.record_baseline import BaselineRecording
from hemolint.b_core.d_domain_model.linter_output import UnparsableOutputError
from hemolint.c_infrastructure.disk_baseline_store import DiskBaselineStore
from hemolint.c_infrastructure.disk_source_lines import DiskSourceLines
from hemolint.d_lib.models import Value

if TYPE_CHECKING:
    from hemolint.b_core.d_domain_model.baseline import BaselineDirectory
    from hemolint.b_core.d_domain_model.drift import Drift
    from hemolint.b_core.d_domain_model.linter_format import LinterFormat
    from hemolint.b_core.d_domain_model.linter_output import LinterOutput
    from hemolint.b_core.d_domain_model.violation import WorkingDirectory


class ExitCode(Value[int]):
    @staticmethod
    def fake() -> ExitCode:
        return ExitCode(0)


class DriftReport(Value[str]):
    @staticmethod
    def fake() -> DriftReport:
        return DriftReport("0 new and 0 fixed violations.\n")

    @staticmethod
    def of(drift: Drift) -> DriftReport:
        lines = [violation.reported_as.root for violation in drift.new]
        fixed = drift.fixed_per_file()
        lines.extend(
            # lint-ignore: NoComment
            f"{file.source.root}: {file.linter.root}-{file.rule.root} ×{count.root} fixed"  # noqa: RUF001
            for file, count in fixed.items()
        )
        if fixed:
            lines.append(
                "Run `hemolint check --prune` to remove fixed violations from the baseline."
            )
        lines.append(f"{len(drift.new)} new and {len(drift.fixed.root)} fixed violations.")
        return DriftReport("".join(f"{line}\n" for line in lines))


class PruneReport(Value[str]):
    @staticmethod
    def fake() -> PruneReport:
        return PruneReport("0 new violations. Removed 0 fixed violations from the baseline.\n")

    @staticmethod
    def of(drift: Drift) -> PruneReport:
        lines = [violation.reported_as.root for violation in drift.new]
        lines.append(
            f"{len(drift.new)} new violations. "
            f"Removed {len(drift.fixed.root)} fixed violations from the baseline."
        )
        return PruneReport("".join(f"{line}\n" for line in lines))


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
            case Err(error):
                return Commands._report_error(error)

    @staticmethod
    def check_baseline(
        output: LinterOutput,
        linter_format: LinterFormat,
        working: WorkingDirectory,
        baseline: BaselineDirectory,
    ) -> ExitCode:
        match BaselineCheck.check(
            output,
            linter_format,
            working,
            DiskSourceLines(working),
            DiskBaselineStore(baseline),
        ):
            case Ok(drift):
                _ = sys.stdout.write(DriftReport.of(drift).root)
                return ExitCode(1) if drift.exists() else ExitCode(0)
            case Err(error):
                return Commands._report_error(error)

    @staticmethod
    def prune_baseline(
        output: LinterOutput,
        linter_format: LinterFormat,
        working: WorkingDirectory,
        baseline: BaselineDirectory,
    ) -> ExitCode:
        match BaselinePruning.prune(
            output,
            linter_format,
            working,
            DiskSourceLines(working),
            DiskBaselineStore(baseline),
        ):
            case Ok(drift):
                _ = sys.stdout.write(PruneReport.of(drift).root)
                return ExitCode(1) if drift.new else ExitCode(0)
            case Err(error):
                return Commands._report_error(error)

    @staticmethod
    def _report_error(error: Exception) -> ExitCode:
        _ = sys.stderr.write(f"{error}\n")
        return ExitCode(2) if isinstance(error, UnparsableOutputError) else ExitCode(1)
