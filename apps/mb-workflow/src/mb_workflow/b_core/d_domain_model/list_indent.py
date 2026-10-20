import re
from enum import StrEnum

from mb_workflow.b_core.d_domain_model.issue import IssueDescription


# How a nested list item is indented. Linear indents it to where its parent's text starts, so two
# spaces under "* " and three under "1. ". Obsidian indents it one tab per level. Linear also puts a
# blank line between a paragraph and the list that follows it, which Obsidian does not need.
class ListIndent(StrEnum):
    linear = "linear"
    obsidian = "obsidian"

    # An item nests under the open item whose text starts at or before the item's marker, reading a
    # tab as running to the next multiple of four columns. Lines other than list items, and lines in
    # code fences, keep their indentation.
    def indented(self, description: IssueDescription) -> IssueDescription:
        item_pattern = re.compile(
            r"(?P<indent>[ \t]*)(?P<marker>[-*+]|\d{1,9}[.)])(?P<rest>[ \t].*)?"
        )
        fence_pattern = re.compile(r"[ \t]*(?:```|~~~)")
        # Per open item, the column its text starts at as read, and as written.
        open_items: list[tuple[int, int]] = []
        fenced = False
        lines: list[str] = []
        # Where the last line of a paragraph sits in lines, until another line follows it.
        paragraph_end: int | None = None
        for line in description.root.split("\n"):
            item = None if fenced else item_pattern.fullmatch(line)
            fence = fence_pattern.match(line) is not None
            if fence:
                fenced = not fenced
            if item is None:
                if line == "" and paragraph_end == len(lines) - 1:
                    lines.append(line)
                    continue
                paragraph_end = None
                if not fenced and line[:1] not in ("", " ", "\t"):
                    open_items.clear()
                    if not fence and not line.startswith("#"):
                        paragraph_end = len(lines)
                lines.append(line)
                continue
            if self == ListIndent.obsidian and paragraph_end == len(lines) - 2:
                _ = lines.pop()
            paragraph_end = None
            column = len(item["indent"].expandtabs(4))
            while open_items and column < open_items[-1][0]:
                _ = open_items.pop()
            match self:
                case ListIndent.linear:
                    indent = " " * (open_items[-1][1] if open_items else 0)
                case ListIndent.obsidian:
                    indent = "\t" * len(open_items)
            marker_width = len(item["marker"]) + 1
            open_items.append((column + marker_width, len(indent) + marker_width))
            lines.append(f"{indent}{item['marker']}{item['rest'] or ''}")
        return IssueDescription("\n".join(lines))
