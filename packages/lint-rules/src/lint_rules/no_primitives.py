from collections.abc import Iterable, Sequence
from typing import ClassVar, Literal, override

import libcst as cst
from fixit import Invalid, LintRule, Valid
from libcst.metadata import CodePosition, CodeRange

Body = Sequence[cst.BaseStatement | cst.BaseSmallStatement]
Surface = Literal["Parameter", "Return type", "Attribute"]
HeadName = Literal["Literal", "bool", "RootModel", "overload", "override", "fixture"]


class TypeNames(frozenset[str]):
    """The names an annotation is built from, e.g. `Name` and `str` for `dict[Name, str]`.

    A generic's own name is left out, so `list[Name]` is as fine as `Name`, but a bare `list` is not.
    """

    @staticmethod
    def of(annotation: cst.BaseExpression) -> TypeNames:
        match annotation:
            case cst.Name(value=name) | cst.Attribute(attr=cst.Name(value=name)):
                # `None` is a value, as in `str | None`.
                return TypeNames() if name == "None" else TypeNames({name})
            case cst.Subscript():
                return TypeNames._of_subscript(annotation)
            case cst.BinaryOperation(left=left, right=right):
                return TypeNames.of_all([left, right])
            case cst.Tuple(elements=elements) | cst.List(elements=elements):
                return TypeNames.of_all(element.value for element in elements)
            case cst.SimpleString():
                parsed = TypeNames.parse_forward_reference(annotation)
                return TypeNames() if parsed is None else TypeNames.of(parsed)
            case _:
                return TypeNames()

    @staticmethod
    def _of_subscript(annotation: cst.Subscript) -> TypeNames:
        # Literal's arguments are values, not types.
        if TypeNames.has_head(annotation.value, "Literal"):
            return TypeNames()
        return TypeNames.of_all(
            element.slice.value
            for element in annotation.slice
            if isinstance(element.slice, cst.Index)
        )

    @staticmethod
    def of_all(annotations: Iterable[cst.BaseExpression]) -> TypeNames:
        return TypeNames(
            frozenset().union(*(TypeNames.of(annotation) for annotation in annotations))
        )

    @staticmethod
    def has_head(expression: cst.BaseExpression, name: HeadName) -> bool:
        head = TypeNames.head(expression)
        return head is not None and head.value == name

    # E.g. `Path` for `pathlib.Path`, `dict` for `dict[str, int]`, `fixture` for `pytest.fixture()`.
    @staticmethod
    def head(expression: cst.BaseExpression) -> cst.Name | None:
        match expression:
            case cst.Name():
                return expression
            case cst.Attribute(attr=name):
                return name
            case cst.Subscript(value=value) | cst.Call(func=value):
                return TypeNames.head(value)
            case _:
                return None

    @staticmethod
    def is_exactly_bool(annotation: cst.BaseExpression) -> bool:
        match annotation:
            case cst.Name() | cst.Attribute():
                return TypeNames.has_head(annotation, "bool")
            case cst.SimpleString():
                parsed = TypeNames.parse_forward_reference(annotation)
                return parsed is not None and TypeNames.is_exactly_bool(parsed)
            case _:
                return False

    @staticmethod
    def parse_forward_reference(annotation: cst.SimpleString) -> cst.BaseExpression | None:
        text = annotation.evaluated_value
        if not isinstance(text, str):
            return None
        try:
            return cst.parse_expression(text)
        except cst.ParserSyntaxError:
            return None


class NoPrimitives(LintRule):
    """TY-c1: never annotate a parameter, return or class attribute with a primitive."""

    DENIED: ClassVar[TypeNames] = TypeNames(
        {
            "int",
            "str",
            "float",
            "bool",
            "bytes",
            "bytearray",
            "complex",
            "Path",
            "PurePath",
            "UUID",
            "datetime",
            "date",
            "time",
            "timedelta",
            "Decimal",
            "Fraction",
            "list",
            "dict",
            "set",
            "frozenset",
            "tuple",
        }
    )
    # A top type says the type is unknown rather than too narrow.
    TOP_TYPES: ClassVar[TypeNames] = TypeNames({"Any", "object"})

    VALID: ClassVar[list[str | Valid]] = [
        Valid("def greet(name: Name) -> None: ..."),
        Valid("def greet(name: Name): ..."),
        Valid("def greet(name) -> None: ..."),
        Valid("def greet(names: list[Name]) -> Names: ..."),
        Valid("def pick(choice: Literal['a', 'b']) -> Name | None: ..."),
        Valid("def is_ready(name: Name) -> bool: ..."),
        Valid("def is_ready(name: Name) -> builtins.bool: ..."),
        Valid("def is_ready(name: Name) -> 'bool': ..."),
        # Annotations outside class bodies are not part of a signature.
        Valid("count: int = 1"),
        Valid(
            """
            def f() -> None:
                count: int = 1
            """
        ),
        Valid(
            """
            class Thing:
                def f(self) -> None:
                    count: int = 1
            """
        ),
        Valid('UserId = NewType("UserId", str)'),
        Valid(
            """
            class Thing:
                UserId = NewType("UserId", str)
            """
        ),
        Valid(
            """
            class Thing:
                def m(self: "Thing") -> None: ...

                @classmethod
                def n(cls: "type[Thing]") -> None: ...
            """
        ),
        Valid(
            """
            class Thing:
                def __init__(self, x: int) -> None: ...

                def __eq__(self, other: object) -> bool: ...
            """
        ),
        # A RootModel is where the primitive is wrapped.
        Valid(
            """
            class Id(RootModel[str]):
                def get(self, key: int) -> str: ...
            """
        ),
        Valid(
            """
            class Id(pydantic.RootModel):
                root: str
            """
        ),
        # The overridden signature dictates the annotations.
        Valid(
            """
            class Thing:
                @override
                def save(self, force: bool) -> str: ...

                @typing.override
                def load(self, force: bool) -> str: ...

                @cache
                @typing_extensions.override
                def drop(self, force: bool) -> str: ...
            """
        ),
        Valid(
            """
            @overload
            def f(x: Name) -> Name: ...
            def f(x: object) -> object: ...
            """
        ),
        # pytest dictates the parameters of tests and fixtures.
        Valid("def test_walks(tmp_path: Path, expected: list[str]) -> None: ..."),
        Valid(
            """
            @pytest.fixture
            def repo(tmp_path: Path) -> Repo: ...

            @fixture
            def other(tmp_path: Path) -> Repo: ...

            @pytest.fixture(scope="session")
            def third(tmp_path: Path) -> Repo: ...
            """
        ),
        # Click decides flag-ness from the annotation being literally bool.
        Valid(
            """
            @app.command()
            def ship(force: bool = False) -> None: ...
            """
        ),
        Valid(
            """
            @app.command()
            def ship(force: Annotated[bool, typer.Option()] = False) -> None: ...
            """
        ),
        Valid(
            """
            @app.command()
            def ship(force: bool | None = None) -> None: ...
            """
        ),
        Valid(
            """
            @app.callback()
            def cli(verbose: bool = False) -> None: ...
            """
        ),
        Valid(
            """
            @cli.command("ship")
            def ship(force: bool = False) -> None: ...
            """
        ),
        Valid(
            """
            @app.command()
            def ship(flags: list[bool]) -> None: ...
            """
        ),
        # Fixit dictates the type of these test-case lists on every rule.
        Valid(
            """
            class Rule(LintRule):
                VALID: ClassVar[list[str | Valid]] = []
                INVALID: ClassVar[list[str | Invalid]] = []
            """
        ),
    ]
    INVALID: ClassVar[list[str | Invalid]] = [
        Invalid("def greet(name: str) -> None: ..."),
        Invalid("def greet(name: builtins.str) -> None: ..."),
        Invalid("def greet(name: 'str') -> None: ..."),
        Invalid("def greet(name: 'list[str]') -> None: ..."),
        Invalid("def greet(name: str | None) -> None: ..."),
        Invalid("def stamp(at: dt.datetime) -> None: ..."),
        Invalid("def read(path: pathlib.Path) -> None: ..."),
        Invalid("def read(path: Path) -> None: ..."),
        Invalid("def greet(names: list) -> None: ..."),
        Invalid("def greet(names: dict[str, UserId]) -> None: ..."),
        Invalid("def greet(on: Callable[[Event], str]) -> None: ..."),
        Invalid("def greet(name: Annotated[str, Field(min_length=1)]) -> None: ..."),
        Invalid("def greet(names: list[list[dict[Name, str]]]) -> None: ..."),
        Invalid("def greet(payload: Any) -> None: ..."),
        Invalid("def greet(payload: dict[str, Any]) -> None: ..."),
        Invalid("def greet(payload: object) -> None: ..."),
        Invalid("def greet(*names: str) -> None: ..."),
        Invalid("def greet(**names: str) -> None: ..."),
        Invalid("def greet(name: str, /) -> None: ..."),
        Invalid("async def greet(*, count: int) -> None: ..."),
        Invalid("def _greet(name: str) -> None: ..."),
        Invalid("def total(name: Name) -> int: ..."),
        Invalid("def payload(name: Name) -> Any: ..."),
        Invalid("def is_ready(name: Name) -> bool | None: ..."),
        Invalid("def flags(name: Name) -> list[bool]: ..."),
        Invalid(
            """
            class Thing:
                def m(self, y: Name) -> str: ...
            """
        ),
        Invalid(
            """
            class Thing:
                count: int
            """
        ),
        Invalid(
            """
            class Thing:
                count: ClassVar[int]
            """
        ),
        Invalid(
            """
            class Thing(TypedDict):
                count: int
            """
        ),
        Invalid(
            """
            class Thing(NamedTuple):
                count: int
            """
        ),
        Invalid(
            """
            class Thing(Protocol):
                count: int
            """
        ),
        Invalid(
            """
            class Thing:
                meta: Any
            """
        ),
        Invalid(
            """
            class Thing:
                class Meta:
                    fields: list[str] = []
            """
        ),
        Invalid(
            """
            def build() -> None:
                class Meta:
                    fields: list[str] = []
            """
        ),
        Invalid(
            """
            class Thing:
                @override_settings(DEBUG=True)
                def save(self, force: Name) -> str: ...
            """
        ),
        # Only the stub is reported, not the implementation.
        Invalid(
            """
            @overload
            def f(x: int) -> Name: ...
            @overload
            def f(x: Name) -> Name: ...
            def f(x: object) -> object: ...
            """,
            range=CodeRange(
                start=CodePosition(line=2, column=9), end=CodePosition(line=2, column=12)
            ),
        ),
        # Only the parameters of a test are pytest's.
        Invalid("def test_walks(x: Name) -> str: ..."),
        Invalid(
            """
            @pytest.fixture
            def repo() -> Path: ...
            """
        ),
        Invalid("def _helper(source: str) -> None: ..."),
        # Only a command's bool parameters are Typer's.
        Invalid(
            """
            @app.command()
            def ship(name: str) -> None: ...
            """
        ),
        Invalid(
            """
            @app.command()
            def ship(name: Annotated[str, typer.Option()]) -> None: ...
            """
        ),
        Invalid(
            """
            @app.command()
            def ship() -> str: ...
            """
        ),
        Invalid(
            """
            @command_runner.run()
            def ship(force: bool = False) -> None: ...
            """
        ),
        Invalid(
            """
            @command
            def ship(force: bool = False) -> None: ...
            """
        ),
        Invalid(
            """
            @app.command()
            def ship(force: bool = False) -> None:
                def inner(raw: bool) -> None: ...
            """
        ),
        Invalid(
            """
            class Thing:
                OTHER: ClassVar[list[str]] = []
            """
        ),
    ]

    @override
    def visit_Module(self, node: cst.Module) -> None:
        self._check_body(node.body)

    # Only definitions directly in a module, class or function body are checked, not those nested in e.g. an `if`.
    def _check_body(self, body: Body) -> None:
        for statement in body:
            if isinstance(statement, cst.FunctionDef):
                self._check_function(statement, body)
            elif isinstance(statement, cst.ClassDef):
                self._check_class(statement)

    def _check_function(self, function: cst.FunctionDef, siblings: Body) -> None:
        if not NoPrimitives._has_exempt_signature(function, siblings):
            self._check_parameters(function)
            if function.returns is not None:
                self._check_return(function.returns)
        self._check_body(function.body.body)

    def _check_parameters(self, function: cst.FunctionDef) -> None:
        # pytest dictates the parameters of tests and fixtures.
        if function.name.value.startswith("test_") or NoPrimitives._decorated_with(
            function, "fixture"
        ):
            return
        owned_by_typer = NoPrimitives._is_typer_command(function)
        for parameter in NoPrimitives._parameters(function):
            if parameter.annotation is None:
                continue
            annotation = parameter.annotation.annotation
            names = TypeNames.of(annotation)
            # Click decides flag-ness from the annotation being literally bool.
            if owned_by_typer and names == {"bool"}:
                continue
            if NoPrimitives._is_flagged(names):
                self._report(annotation, "Parameter", parameter.name)

    def _check_return(self, returns: cst.Annotation) -> None:
        annotation = returns.annotation
        names = TypeNames.of(annotation)
        # A predicate's bool has no better spelling.
        denied = names & NoPrimitives.DENIED and not TypeNames.is_exactly_bool(annotation)
        if denied or names & NoPrimitives.TOP_TYPES:
            self._report(annotation, "Return type", None)

    def _check_class(self, class_def: cst.ClassDef) -> None:
        # A RootModel is where a primitive gets wrapped.
        if any(TypeNames.has_head(base.value, "RootModel") for base in class_def.bases):
            return
        body = class_def.body.body
        for statement in NoPrimitives._small_statements(body):
            if isinstance(statement, cst.AnnAssign) and not NoPrimitives._is_fixit_test_cases(
                statement.target
            ):
                names = TypeNames.of(statement.annotation.annotation)
                if NoPrimitives._is_flagged(names):
                    self._report(statement.annotation.annotation, "Attribute", statement.target)
        self._check_body(body)

    def _report(
        self, annotation: cst.BaseExpression, surface: Surface, named: cst.BaseExpression | None
    ) -> None:
        empty = cst.Module(body=[])
        subject = surface if named is None else f'{surface} "{empty.code_for_node(named)}"'
        self.report(
            annotation,
            f'{subject} is annotated "{empty.code_for_node(annotation)}". '
            "Use a domain type, e.g. a Pydantic RootModel, instead of a primitive (TY-c1).",
        )

    @staticmethod
    def _is_flagged(names: TypeNames) -> bool:
        return bool(names & (NoPrimitives.DENIED | NoPrimitives.TOP_TYPES))

    @staticmethod
    def _has_exempt_signature(function: cst.FunctionDef, siblings: Body) -> bool:
        name = function.name.value
        is_dunder = name.startswith("__") and name.endswith("__")
        # The overloads above the implementation carry its signature.
        is_overload_implementation = not NoPrimitives._decorated_with(function, "overload") and any(
            isinstance(sibling, cst.FunctionDef)
            and sibling.name.value == name
            and NoPrimitives._decorated_with(sibling, "overload")
            for sibling in siblings
        )
        return (
            is_dunder
            or is_overload_implementation
            or NoPrimitives._decorated_with(function, "override")
        )

    @staticmethod
    def _decorated_with(function: cst.FunctionDef, name: HeadName) -> bool:
        return any(
            TypeNames.has_head(decorator.decorator, name) for decorator in function.decorators
        )

    # Matched on the attribute the app object is asked for, e.g. `@app.command()`, so it holds
    # however that object is named. A bare `@command`, which Typer never spells, stays checked.
    @staticmethod
    def _is_typer_command(function: cst.FunctionDef) -> bool:
        return any(
            name is not None and name.value in {"command", "callback"}
            for name in (
                NoPrimitives._attribute_name(decorator.decorator)
                for decorator in function.decorators
            )
        )

    @staticmethod
    def _attribute_name(decorator: cst.BaseExpression) -> cst.Name | None:
        match decorator:
            case cst.Attribute(attr=name):
                return name
            case cst.Call(func=func):
                return NoPrimitives._attribute_name(func)
            case _:
                return None

    @staticmethod
    def _parameters(function: cst.FunctionDef) -> list[cst.Param]:
        params = function.params
        every = [
            *params.posonly_params,
            *params.params,
            *params.kwonly_params,
            params.star_arg,
            params.star_kwarg,
        ]
        return [
            parameter
            for parameter in every
            if isinstance(parameter, cst.Param) and parameter.name.value not in {"self", "cls"}
        ]

    @staticmethod
    def _small_statements(body: Body) -> list[cst.BaseSmallStatement]:
        return [
            small
            for statement in body
            for small in (
                statement.body if isinstance(statement, cst.SimpleStatementLine) else [statement]
            )
            if isinstance(small, cst.BaseSmallStatement)
        ]

    # Fixit dictates the type of these test-case lists on every rule.
    @staticmethod
    def _is_fixit_test_cases(target: cst.BaseAssignTargetExpression) -> bool:
        return isinstance(target, cst.Name) and target.value in {"VALID", "INVALID"}
