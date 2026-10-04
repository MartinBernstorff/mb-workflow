from typing import TYPE_CHECKING, Protocol, override

from safe_result import Err, Ok, Result

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hemolint.b_core.d_domain_model.violation import (
        LineNumber,
        SourceLine,
        SourcePath,
        SourceText,
    )


class MissingSourceLineError(Exception):
    pass


class SourceLines(Protocol):
    def read(
        self, source: SourcePath, line: LineNumber
    ) -> Result[SourceLine, MissingSourceLineError]: ...


class FakeSourceLines(SourceLines):
    def __init__(self, files: Mapping[SourcePath, SourceText]) -> None:
        self._files = dict(files)

    @override
    def read(
        self, source: SourcePath, line: LineNumber
    ) -> Result[SourceLine, MissingSourceLineError]:
        text = self._files.get(source)
        if text is None:
            return Err(MissingSourceLineError(f"{source.root} does not exist."))
        found = text.line(line)
        if found is None:
            return Err(MissingSourceLineError(f"{source.root} has no line {line.root}."))
        return Ok(found)
