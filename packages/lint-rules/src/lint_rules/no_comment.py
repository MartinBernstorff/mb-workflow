from typing import TYPE_CHECKING, ClassVar, cast, override

import libcst as cst
from fixit import CodePosition, CodeRange, Invalid, LintRule, Valid
from fixit.ftypes import LintIgnoreRegex
from libcst.metadata import CodePosition as NodePosition
from libcst.metadata import CodeRange as NodeRange
from libcst.metadata import PositionProvider

if TYPE_CHECKING:
    from collections.abc import Sequence


class NoComment(LintRule):
    MESSAGE = "Say it in the code instead of in a comment or docstring (CM-1)."

    VALID: ClassVar[list[str | Valid]] = [
        Valid("total = price * quantity"),
        Valid(
            """
            total = 1
            "a string expression after the first statement is not a docstring"
            """
        ),
        Valid(
            """
            # lint-ignore: NoComment
            # kept
            # kept too
            total = 1
            """
        ),
        Valid(
            """
            # lint-ignore: NoComment
            total = compute()  # type: ignore
            """
        ),
        Valid(
            """
            def drain() -> None:
                # lint-ignore: NoComment
                \"\"\"Drain the queue.\"\"\"
            """
        ),
        Valid(
            """
            # lint-ignore: NoRaise
            raise ValueError("unreadable")
            """
        ),
        Valid(
            """
            # lint-fixme: NoRaise
            raise ValueError("unreadable")
            """
        ),
    ]
    INVALID: ClassVar[list[str | Invalid]] = [
        Invalid(
            """
            # the total
            total = 1
            """
        ),
        Invalid("total = compute()  # noqa: E501"),
        Invalid('"""The module."""'),
        Invalid(
            """
            def drain() -> None:
                \"\"\"Drain the queue.\"\"\"
            """
        ),
        Invalid(
            """
            class Queue:
                \"\"\"A queue.\"\"\"
            """
        ),
        Invalid(
            """
            # lint-ignore: NoRaise
            # the total
            total = 1
            """
        ),
        Invalid(
            """
            # lint-ignore: NoComment
            # kept

            # flagged
            total = 1
            """,
            range=CodeRange(
                start=CodePosition(line=4, column=0), end=CodePosition(line=4, column=9)
            ),
        ),
        Invalid(
            """
            # lint-ignore: NoComment
            def drain() -> None:
                # flagged
                pass
            """,
            range=CodeRange(
                start=CodePosition(line=3, column=4), end=CodePosition(line=3, column=13)
            ),
        ),
        Invalid(
            """
            # lint-ignore: NoComment
            def drain() -> None:
                \"\"\"Drain the queue.\"\"\"
            """,
            range=CodeRange(
                start=CodePosition(line=3, column=4), end=CodePosition(line=3, column=26)
            ),
        ),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._flagged: list[cst.CSTNode] = []
        self._own_line_comments: dict[int, cst.Comment] = {}

    @override
    def visit_Comment(self, node: cst.Comment) -> None:
        if isinstance(self.get_metadata(cst.metadata.ParentNodeProvider, node), cst.EmptyLine):
            self._own_line_comments[self._start(node).line] = node
        if LintIgnoreRegex.search(node.value) is None:
            self._flagged.append(node)

    @override
    def visit_Module(self, node: cst.Module) -> None:
        self._flagged.clear()
        self._own_line_comments.clear()
        self._flag_docstring(node.body)

    @override
    def visit_ClassDef(self, node: cst.ClassDef) -> None:
        self._flag_docstring(node.body.body)

    @override
    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        self._flag_docstring(node.body.body)

    @override
    def leave_Module(self, original_node: cst.Module) -> None:
        for node in self._flagged:
            if not self._exempt(node):
                self.report(node)

    @override
    def ignore_lint(self, node: cst.CSTNode) -> bool:
        return False

    def _flag_docstring(self, body: Sequence[cst.BaseStatement | cst.BaseSmallStatement]) -> None:
        first = body[0] if body else None
        if isinstance(first, cst.SimpleStatementLine):
            first = first.body[0]
        if isinstance(first, cst.Expr) and isinstance(
            first.value, cst.SimpleString | cst.ConcatenatedString
        ):
            self._flagged.append(first.value)

    def _exempt(self, node: cst.CSTNode) -> bool:
        line = self._start(node).line - 1
        while (comment := self._own_line_comments.get(line)) is not None:
            if self._is_exemption(comment):
                return True
            line -= 1
        return False

    def _is_exemption(self, comment: cst.Comment) -> bool:
        match = LintIgnoreRegex.search(comment.value)
        if match is None:
            return False
        names = match.group(2)
        return names is None or self.name in (name.strip() for name in names.split(","))

    def _start(self, node: cst.CSTNode) -> NodePosition:
        return cast("NodeRange", self.get_metadata(PositionProvider, node)).start
