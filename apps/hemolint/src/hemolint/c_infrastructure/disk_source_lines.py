from typing import override

from safe_result import Err, Result

from hemolint.b_core.c_secondary_ports.source_lines import SourceLines
from hemolint.b_core.d_domain_model.violation import (
    LineNumber,
    MissingSourceLineError,
    SourceLine,
    SourcePath,
    SourceText,
    WorkingDirectory,
)


class DiskSourceLines(SourceLines):
    def __init__(self, directory: WorkingDirectory) -> None:
        self._directory = directory
        self._texts: dict[SourcePath, SourceText] = {}

    @override
    def read(
        self, source: SourcePath, line: LineNumber
    ) -> Result[SourceLine, MissingSourceLineError]:
        text = self._texts.get(source)
        if text is None:
            try:
                text = SourceText((self._directory.root / source.root).read_text())
            except (OSError, UnicodeDecodeError) as error:
                return Err(MissingSourceLineError(f"Cannot read {source.root}: {error}"))
            self._texts[source] = text
        return text.line_at(source, line)
