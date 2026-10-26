from collections import Counter
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from hemolint.b_core.d_domain_model.violation import (
    Fingerprint,
    LinterLine,
    LinterName,
    RuleName,
    SourcePath,
)
from hemolint.d_lib.models import Model, Value

if TYPE_CHECKING:
    from collections.abc import Iterable


class BaselineDirectory(Value[Path]):
    @staticmethod
    def fake() -> BaselineDirectory:
        return BaselineDirectory(Path("/Users/me/project/.hemolint"))


# The violations of one rule in one source file, which the disk baseline keeps in one file.
class BaselineFile(Model):
    source: SourcePath
    linter: LinterName
    rule: RuleName

    @staticmethod
    def fake() -> BaselineFile:
        return BaselineFile(
            source=SourcePath.fake(), linter=LinterName.fake(), rule=RuleName.fake()
        )


# How a recorded baseline matches the violations found later.
class BaselineMatching(StrEnum):
    # Each violation by its fingerprint, so an edit to its line makes it new.
    by_fingerprint = "fingerprint"
    # Only how many violations of a rule a source file holds, so edits within the file never drift.
    by_count = "count"


# A counted violation has no fingerprint: it matches any violation of its rule in its source file.
class Violation(Model):
    file: BaselineFile
    fingerprint: Fingerprint | None

    @staticmethod
    def fake() -> Violation:
        return Violation(file=BaselineFile.fake(), fingerprint=Fingerprint.fake())

    @staticmethod
    def counted(file: BaselineFile) -> Violation:
        return Violation(file=file, fingerprint=None)

    def is_counted(self) -> bool:
        return self.fingerprint is None

    # Global diagnostics keep their fingerprints, since they come from the linter, not a line.
    def matched_by(self, matching: BaselineMatching) -> Violation:
        if matching == BaselineMatching.by_fingerprint or (
            self.file.source == SourcePath.global_diagnostics()
        ):
            return self
        return Violation.counted(self.file)


# A violation in the current linter output, with the line the linter reported it on.
class FoundViolation(Model):
    violation: Violation
    reported_as: LinterLine

    @staticmethod
    def fake() -> FoundViolation:
        return FoundViolation(violation=Violation.fake(), reported_as=LinterLine.fake())


class Count(Value[int]):
    @staticmethod
    def fake() -> Count:
        return Count(1)


class BaselineChange(Model):
    added: Count
    removed: Count

    @staticmethod
    def fake() -> BaselineChange:
        return BaselineChange(added=Count.fake(), removed=Count(0))


# A sorted multiset: a violation held twice is two copies of the same violation.
class Baseline(Value[tuple[Violation, ...]]):
    @staticmethod
    def fake() -> Baseline:
        return Baseline.of((Violation.fake(),))

    @staticmethod
    def of(violations: Iterable[Violation]) -> Baseline:
        return Baseline(
            tuple(
                sorted(
                    violations,
                    key=lambda violation: (
                        violation.file.source.root,
                        violation.file.linter.root,
                        violation.file.rule.root,
                        "" if violation.fingerprint is None else violation.fingerprint.root,
                    ),
                )
            )
        )

    def of_linter(self, linter: LinterName) -> Baseline:
        return Baseline(
            tuple(violation for violation in self.root if violation.file.linter == linter)
        )

    # Removes one held copy per copy in the other baseline.
    def without(self, other: Baseline) -> Baseline:
        return Baseline.of((Counter(self.root) - Counter(other.root)).elements())

    def change_from(self, previous: Baseline) -> BaselineChange:
        now, before = Counter(self.root), Counter(previous.root)
        return BaselineChange(
            added=Count((now - before).total()), removed=Count((before - now).total())
        )
