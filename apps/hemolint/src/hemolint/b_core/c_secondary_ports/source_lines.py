from typing import TYPE_CHECKING, Protocol, override

from safe_result import Err, Result

from hemolint.b_core.d_domain_model.violation import MissingSourceLineError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hemolint.b_core.d_domain_model.violation import (
        LineNumber,
        SourceLine,
        SourcePath,
        SourceText,
    )


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
        return text.line_at(source, line)
