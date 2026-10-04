from typing import ClassVar, override

import libcst as cst
from fixit import Invalid, LintRule, Valid


class NoDunderAll(LintRule):
    """MO-t8: never maintain an `__all__` list; import names directly instead."""

    MESSAGE = "Don't maintain `__all__`. Import names directly instead (MO-t8)."

    VALID: ClassVar[list[str | Valid]] = [
        Valid("names = ['a', 'b']"),
        Valid("print(__all__)"),
        Valid("module.__all__ = ['a']"),
    ]
    INVALID: ClassVar[list[str | Invalid]] = [
        Invalid("__all__ = ['a', 'b']"),
        Invalid("__all__: list[str] = ['a']"),
        Invalid("__all__ += ['a']"),
        Invalid("__all__ = names = ['a']"),
    ]

    @override
    def visit_Assign(self, node: cst.Assign) -> None:
        if any(NoDunderAll._is_dunder_all(target.target) for target in node.targets):
            self.report(node)

    @override
    def visit_AnnAssign(self, node: cst.AnnAssign) -> None:
        if NoDunderAll._is_dunder_all(node.target):
            self.report(node)

    @override
    def visit_AugAssign(self, node: cst.AugAssign) -> None:
        if NoDunderAll._is_dunder_all(node.target):
            self.report(node)

    @staticmethod
    def _is_dunder_all(target: cst.BaseExpression) -> bool:
        return isinstance(target, cst.Name) and target.value == "__all__"
