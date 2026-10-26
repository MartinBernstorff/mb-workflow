from collections import Counter
from typing import TYPE_CHECKING

from hemolint.b_core.d_domain_model.baseline import (
    Baseline,
    BaselineFile,
    Count,
    FoundViolation,
    Violation,
)
from hemolint.d_lib.models import Model

if TYPE_CHECKING:
    from collections.abc import Iterable


# A counted baseline file and every violation of its rule found in its source file.
class CountDrift(Model):
    file: BaselineFile
    found: tuple[FoundViolation, ...]
    baseline: Count

    @staticmethod
    def fake() -> CountDrift:
        return CountDrift(
            file=BaselineFile.fake(), found=(FoundViolation.fake(),), baseline=Count(0)
        )

    def new_count(self) -> Count:
        return Count(max(len(self.found) - self.baseline.root, 0))

    def fixed_count(self) -> Count:
        return Count(max(self.baseline.root - len(self.found), 0))


# How the baseline differs from the current violations.
class Drift(Model):
    new: tuple[FoundViolation, ...]
    fixed: Baseline
    counted: tuple[CountDrift, ...]

    @staticmethod
    def fake() -> Drift:
        return Drift(new=(FoundViolation.fake(),), fixed=Baseline.of(()), counted=())

    # Copies of a violation match baselined copies in output order, so the later ones are new.
    # In a counted baseline file, only the number of violations matters.
    @staticmethod
    def between(baseline: Baseline, found: Iterable[FoundViolation]) -> Drift:
        counts = Counter(violation.file for violation in baseline.root if violation.is_counted())
        in_counted: dict[BaselineFile, list[FoundViolation]] = {file: [] for file in counts}
        unmatched = Counter(violation for violation in baseline.root if not violation.is_counted())
        new: list[FoundViolation] = []
        for reported in found:
            if reported.violation.file in in_counted:
                in_counted[reported.violation.file].append(reported)
            elif unmatched[reported.violation] > 0:
                unmatched[reported.violation] -= 1
            else:
                new.append(reported)
        counted = (
            CountDrift(file=file, found=tuple(reported), baseline=Count(counts[file]))
            for file, reported in in_counted.items()
        )
        return Drift(
            new=tuple(new),
            fixed=Baseline.of(unmatched.elements()),
            counted=tuple(drift for drift in counted if len(drift.found) != drift.baseline.root),
        )

    def exists(self) -> bool:
        return bool(self.new or self.fixed.root or self.counted)

    def new_count(self) -> Count:
        return Count(len(self.new) + sum(drift.new_count().root for drift in self.counted))

    # Every fixed violation, counted ones as copies without a fingerprint.
    def all_fixed(self) -> Baseline:
        counted = (
            Violation.counted(drift.file)
            for drift in self.counted
            for _ in range(drift.fixed_count().root)
        )
        return Baseline.of((*self.fixed.root, *counted))

    def fixed_per_file(self) -> dict[BaselineFile, Count]:
        counts = Counter(violation.file for violation in self.fixed.root)
        return {file: Count(count) for file, count in counts.items()}
