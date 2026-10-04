from typing import ClassVar, override

import libcst as cst
from fixit import Invalid, LintRule, Valid
from libcst.helpers import get_full_name_for_node


class NoRaise(LintRule):
    """TY-7e: return errors as values instead of raising them."""

    MESSAGE = "Return the error as a value instead of raising it (TY-7e)."

    VALID: ClassVar[list[str | Valid]] = [
        Valid(
            """
            try:
                start()
            except Exception:
                release()
                raise
            """
        ),
        Valid(
            """
            class Limit(BaseModel):
                @field_validator("value")
                @classmethod
                def positive(cls, value: int) -> int:
                    if value < 0:
                        raise ValueError("negative")
                    return value
            """
        ),
        Valid(
            """
            class Directory(RootModel[Path]):
                @pydantic.model_validator(mode="after")
                def exists(self) -> Directory:
                    if not self.root.is_dir():
                        raise ValueError("missing")
                    return self
            """
        ),
        Valid(
            """
            def handle(number: int) -> None:
                raise SystemExit(128 + number)
            """
        ),
    ]
    INVALID: ClassVar[list[str | Invalid]] = [
        Invalid(
            """
            def parse() -> None:
                raise ValueError("unreadable")
            """
        ),
        Invalid(
            """
            try:
                parse()
            except ValueError as error:
                raise error
            """
        ),
        Invalid(
            """
            try:
                parse()
            except ValueError as error:
                raise ParseError("unreadable") from error
            """
        ),
        Invalid(
            """
            class Directory(RootModel[Path]):
                @staticmethod
                def of(path: Path) -> Directory:
                    raise ValueError("missing")
            """
        ),
        Invalid(
            """
            def drain() -> None:
                raise typer.Exit(code=1)
            """
        ),
    ]

    @override
    def visit_Raise(self, node: cst.Raise) -> None:
        if node.exc is None or self._inside_validator(node):
            return
        if not self._is_allowed_exception(node.exc):
            self.report(node)

    def _is_allowed_exception(self, raised: cst.BaseExpression) -> bool:
        return get_full_name_for_node(raised) == "SystemExit"

    # Pydantic turns a raise in a validator into a ValidationError, so the raise is how a validator reports.
    def _inside_validator(self, node: cst.CSTNode) -> bool:
        validators = {"field_validator", "model_validator", "validator", "root_validator"}
        parent = self.get_metadata(cst.metadata.ParentNodeProvider, node, None)
        while parent is not None:
            if isinstance(parent, cst.FunctionDef) and any(
                (get_full_name_for_node(decorator.decorator) or "").rsplit(".", 1)[-1] in validators
                for decorator in parent.decorators
            ):
                return True
            parent = self.get_metadata(cst.metadata.ParentNodeProvider, parent, None)
        return False


class NoRaiseAtTyperBoundary(NoRaise):
    """NoRaise for a CLI package, where Typer's own exceptions are how a command exits."""

    VALID: ClassVar[list[str | Valid]] = [
        Valid(
            """
            def drain() -> None:
                raise typer.BadParameter("--dry-run cannot be combined with --watch.")
            """
        ),
        Valid(
            """
            def drain() -> None:
                raise typer.Exit(code=1)
            """
        ),
    ]
    INVALID: ClassVar[list[str | Invalid]] = [
        Invalid(
            """
            def drain() -> None:
                raise ValueError("unreadable")
            """
        ),
    ]

    @override
    def _is_allowed_exception(self, raised: cst.BaseExpression) -> bool:
        # E.g. `typer.Exit` for `raise typer.Exit(code=1)`.
        dotted_name = get_full_name_for_node(raised) or ""
        return super()._is_allowed_exception(raised) or dotted_name.startswith("typer.")
