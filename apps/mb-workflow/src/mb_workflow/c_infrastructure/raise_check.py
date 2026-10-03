import ast
from pathlib import Path
from typing import TYPE_CHECKING, override

from mb_workflow.d_lib.models import Model, Value

if TYPE_CHECKING:
    from mb_workflow.c_infrastructure.shell import ExistingDirectory


class SourceFile(Value[Path]):
    @staticmethod
    def fake() -> SourceFile:
        return SourceFile(Path("mb_workflow/b_core/a_features/drain.py"))


class ModuleName(Value[str]):
    @staticmethod
    def fake() -> ModuleName:
        return ModuleName("mb_workflow.b_core.a_features.drain")

    @staticmethod
    def of_file(root: ExistingDirectory, source: SourceFile) -> ModuleName:
        parts = source.root.relative_to(root.root).with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        return ModuleName(".".join(parts))

    def at_typer_boundary(self, typer_package: ModuleName) -> TyperBoundary:
        return TyperBoundary(
            self.root == typer_package.root or self.root.startswith(f"{typer_package.root}.")
        )


class RaiseCount(Value[int]):
    @staticmethod
    def fake() -> RaiseCount:
        return RaiseCount(1)


class RaiseCounts(Value[dict[ModuleName, RaiseCount]]):
    @staticmethod
    def fake() -> RaiseCounts:
        return RaiseCounts({ModuleName.fake(): RaiseCount.fake()})


# Whether the module sits in the CLI package, where Typer's own exceptions are how a command exits.
class TyperBoundary(Value[bool]):
    @staticmethod
    def fake() -> TyperBoundary:
        return TyperBoundary(False)


class OverrunReport(Value[str]):
    @staticmethod
    def fake() -> OverrunReport:
        return OverrunReport.of(Overrun.fake())

    @staticmethod
    def of(overrun: Overrun) -> OverrunReport:
        return OverrunReport(
            f"{overrun.module.root} has {overrun.found.root} disallowed raises, "
            f"but its baseline allows {overrun.baseline.root}. Return the error as a value instead."
        )


class Overrun(Model):
    module: ModuleName
    baseline: RaiseCount
    found: RaiseCount

    @staticmethod
    def fake() -> Overrun:
        return Overrun(module=ModuleName.fake(), baseline=RaiseCount(1), found=RaiseCount(2))


# The dotted name an expression calls or names, e.g. `typer.Exit` for `typer.Exit(code=1)`.
class Callee(Value[str]):
    @staticmethod
    def fake() -> Callee:
        return Callee("typer.Exit")

    @staticmethod
    def of(node: ast.expr) -> Callee:
        if isinstance(node, ast.Call):
            return Callee.of(node.func)
        if isinstance(node, ast.Attribute):
            return Callee(f"{Callee.of(node.value).root}.{node.attr}")
        if isinstance(node, ast.Name):
            return Callee(node.id)
        return Callee("")


class _RaiseCounter(ast.NodeVisitor):
    def __init__(self, boundary: TyperBoundary) -> None:
        self._boundary = boundary
        self._validator_depth = 0
        self.flagged = 0

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    @override
    def visit_Raise(self, node: ast.Raise) -> None:
        if self._validator_depth == 0 and not self._allowed(node):
            self.flagged += 1
        self.generic_visit(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        validator = any(
            Callee.of(decorator).root.rsplit(".", 1)[-1]
            in {"field_validator", "model_validator", "validator", "root_validator"}
            for decorator in node.decorator_list
        )
        self._validator_depth += validator
        self.generic_visit(node)
        self._validator_depth -= validator

    def _allowed(self, node: ast.Raise) -> bool:
        if node.exc is None:
            return True
        callee = Callee.of(node.exc).root
        return callee == "SystemExit" or (self._boundary.root and callee.startswith("typer."))


class RaiseCheck:
    @staticmethod
    def count(tree: ast.Module, boundary: TyperBoundary) -> RaiseCount:
        counter = _RaiseCounter(boundary)
        counter.visit(tree)
        return RaiseCount(counter.flagged)

    @staticmethod
    def scan(root: ExistingDirectory, typer_package: ModuleName) -> RaiseCounts:
        found: dict[ModuleName, RaiseCount] = {}
        for path in sorted(root.root.rglob("*.py")):
            module = ModuleName.of_file(root, SourceFile(path))
            count = RaiseCheck.count(
                ast.parse(path.read_text()), module.at_typer_boundary(typer_package)
            )
            if count.root > 0:
                found[module] = count
        return RaiseCounts(found)


class BaselineDirectory(Value[Path]):
    @staticmethod
    def fake() -> BaselineDirectory:
        return BaselineDirectory(Path("raise-baseline"))

    def file_for(self, module: ModuleName) -> BaselineFile:
        return BaselineFile(self.root / f"{module.root}.txt")


class BaselineFile(Value[Path]):
    @staticmethod
    def fake() -> BaselineFile:
        return BaselineDirectory.fake().file_for(ModuleName.fake())


# One file per module, so parallel branches that burn down different modules never conflict.
class RaiseBaseline:
    def __init__(self, directory: BaselineDirectory) -> None:
        self._directory = directory

    def counts(self) -> RaiseCounts:
        if not self._directory.root.is_dir():
            return RaiseCounts({})
        return RaiseCounts(
            {
                ModuleName(path.stem): RaiseCount(int(path.read_text()))
                for path in sorted(self._directory.root.glob("*.txt"))
            }
        )

    def record(self, module: ModuleName, count: RaiseCount) -> None:
        path = self._directory.file_for(module).root
        if count.root == 0:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(f"{count.root}\n")

    # Lowers the baseline of every module that now raises less, and returns the modules that overrun it.
    def burn_down(self, found: RaiseCounts) -> tuple[Overrun, ...]:
        recorded = self.counts().root
        overruns: list[Overrun] = []
        names = sorted(module.root for module in recorded.keys() | found.root.keys())
        for module in map(ModuleName, names):
            baseline = recorded.get(module, RaiseCount(0))
            count = found.root.get(module, RaiseCount(0))
            if count.root > baseline.root:
                overruns.append(Overrun(module=module, baseline=baseline, found=count))
            elif count.root < baseline.root:
                self.record(module, count)
        return tuple(overruns)
