from collections import Counter
from typing import TYPE_CHECKING

from hemolint.b_core.d_domain_model.baseline import Baseline, BaselineFile, Count, FoundViolation
from hemolint.d_lib.models import Model

if TYPE_CHECKING:
    from collections.abc import Iterable


# How the baseline differs from the current violations.
class Drift(Model):
    new: tuple[FoundViolation, ...]
    fixed: Baseline

    @staticmethod
    def fake() -> Drift:
        return Drift(new=(FoundViolation.fake(),), fixed=Baseline.of(()))

    # Copies of a violation match baselined copies in output order, so the later ones are new.
    @staticmethod
    def between(baseline: Baseline, found: Iterable[FoundViolation]) -> Drift:
        unmatched = Counter(baseline.root)
        new: list[FoundViolation] = []
        for reported in found:
            if unmatched[reported.violation] > 0:
                unmatched[reported.violation] -= 1
            else:
                new.append(reported)
        return Drift(new=tuple(new), fixed=Baseline.of(unmatched.elements()))

    def exists(self) -> bool:
        return bool(self.new or self.fixed.root)

    def fixed_per_file(self) -> dict[BaselineFile, Count]:
        counts = Counter(violation.file for violation in self.fixed.root)
        return {file: Count(count) for file, count in counts.items()}
