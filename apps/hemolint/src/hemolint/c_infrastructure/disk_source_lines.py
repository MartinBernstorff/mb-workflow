from typing import override

from safe_result import Err, Ok, Result

from hemolint.b_core.c_secondary_ports.source_lines import MissingSourceLineError, SourceLines
from hemolint.b_core.d_domain_model.violation import (
    LineNumber,
    SourceLine,
    SourcePath,
    SourceText,
    WorkingDirectory,
)


class DiskSourceLines(SourceLines):
    def __init__(self, directory: WorkingDirectory) -> None:
        self._directory = directory
        # A file with many violations is read once.
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
        found = text.line(line)
        if found is None:
            return Err(MissingSourceLineError(f"{source.root} has no line {line.root}."))
        return Ok(found)
