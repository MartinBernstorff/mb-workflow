import os
from pathlib import Path

from safe_result import Err, Ok, Result

from hemolint.d_lib.models import Model, Value


class OutsideWorkingDirectoryError(Exception):
    pass


class MissingSourceLineError(Exception):
    pass


class WorkingDirectory(Value[Path]):
    @staticmethod
    def fake() -> WorkingDirectory:
        return WorkingDirectory(Path("/Users/me/project"))

    @staticmethod
    def current() -> WorkingDirectory:
        return WorkingDirectory(Path.cwd())


class SourcePath(Value[Path]):
    @staticmethod
    def fake() -> SourcePath:
        return SourcePath(Path("src/app.py"))

    @staticmethod
    def global_diagnostics() -> SourcePath:
        return SourcePath(Path("_global"))

    def relative_to_working_directory(
        self, directory: WorkingDirectory
    ) -> Result[SourcePath, OutsideWorkingDirectoryError]:
        placed = Path(os.path.normpath(directory.root / self.root))
        if not placed.is_relative_to(directory.root):
            return Err(
                OutsideWorkingDirectoryError(
                    f"{self.root} is outside the working directory {directory.root}."
                )
            )
        return Ok(SourcePath(placed.relative_to(directory.root)))


class LineNumber(Value[int]):
    @staticmethod
    def fake() -> LineNumber:
        return LineNumber(1)


class RuleName(Value[str]):
    @staticmethod
    def fake() -> RuleName:
        return RuleName("CompareSingletonPrimitivesByIs")


class LinterName(Value[str]):
    @staticmethod
    def fake() -> LinterName:
        return LinterName("fixit")


class LinterLine(Value[str]):
    @staticmethod
    def fake() -> LinterLine:
        return LinterLine("src/app.py@1:3 CompareSingletonPrimitivesByIs: Use `is`.")


class LocatedViolation(Model):
    source: SourcePath
    line: LineNumber
    rule: RuleName
    reported_as: LinterLine

    @staticmethod
    def fake() -> LocatedViolation:
        return LocatedViolation(
            source=SourcePath.fake(),
            line=LineNumber.fake(),
            rule=RuleName.fake(),
            reported_as=LinterLine.fake(),
        )


class SourceLine(Value[str]):
    @staticmethod
    def fake() -> SourceLine:
        return SourceLine("    if x == None:")


class SourceText(Value[str]):
    @staticmethod
    def fake() -> SourceText:
        return SourceText("if x == None:\n    pass\n")

    def line_at(
        self, source: SourcePath, number: LineNumber
    ) -> Result[SourceLine, MissingSourceLineError]:
        lines = self.root.splitlines()
        if not 1 <= number.root <= len(lines):
            return Err(MissingSourceLineError(f"{source.root} has no line {number.root}."))
        return Ok(SourceLine(lines[number.root - 1]))


class Fingerprint(Value[str]):
    @staticmethod
    def fake() -> Fingerprint:
        return Fingerprint.of(SourceLine.fake())

    @staticmethod
    def of(line: SourceLine) -> Fingerprint:
        return Fingerprint(line.root.strip())


class GlobalViolation(Model):
    rule: RuleName
    fingerprint: Fingerprint
    reported_as: LinterLine

    @staticmethod
    def fake() -> GlobalViolation:
        return GlobalViolation(
            rule=RuleName.fake(), fingerprint=Fingerprint.fake(), reported_as=LinterLine.fake()
        )
