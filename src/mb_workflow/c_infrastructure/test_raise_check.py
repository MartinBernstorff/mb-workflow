import ast
from pathlib import Path
from textwrap import dedent

from mb_workflow.c_infrastructure.raise_check import (
    BaselineDirectory,
    ModuleName,
    Overrun,
    OverrunReport,
    RaiseBaseline,
    RaiseCheck,
    RaiseCount,
    RaiseCounts,
    TyperBoundary,
)
from mb_workflow.c_infrastructure.shell import ExistingDirectory


def test_flags_a_raised_error() -> None:
    source = ast.parse(
        dedent(
            """
            def parse() -> None:
                raise ValueError("unreadable")
            """
        )
    )
    expected = RaiseCount(1)
    assert RaiseCheck.count(source, TyperBoundary(False)) == expected


def test_flags_every_raise_in_a_module() -> None:
    source = ast.parse(
        dedent(
            """
            def parse() -> None:
                raise ValueError("unreadable")

            class Parser:
                def parse(self) -> None:
                    raise ParseError("unreadable")
            """
        )
    )
    expected = RaiseCount(2)
    assert RaiseCheck.count(source, TyperBoundary(False)) == expected


def test_flags_a_reraise_of_a_named_error() -> None:
    source = ast.parse(
        dedent(
            """
            try:
                parse()
            except ValueError as error:
                raise error
            """
        )
    )
    expected = RaiseCount(1)
    assert RaiseCheck.count(source, TyperBoundary(False)) == expected


def test_allows_a_bare_reraise() -> None:
    source = ast.parse(
        dedent(
            """
            try:
                start()
            except Exception:
                release()
                raise
            """
        )
    )
    expected = RaiseCount(0)
    assert RaiseCheck.count(source, TyperBoundary(False)) == expected


def test_allows_a_raise_in_a_field_validator() -> None:
    source = ast.parse(
        dedent(
            """
            class Limit(BaseModel):
                @field_validator("value")
                @classmethod
                def positive(cls, value: int) -> int:
                    if value < 0:
                        raise ValueError("negative")
                    return value
            """
        )
    )
    expected = RaiseCount(0)
    assert RaiseCheck.count(source, TyperBoundary(False)) == expected


def test_allows_a_raise_in_a_model_validator_named_through_its_module() -> None:
    source = ast.parse(
        dedent(
            """
            class Directory(RootModel[Path]):
                @pydantic.model_validator(mode="after")
                def exists(self) -> Directory:
                    if not self.root.is_dir():
                        raise ValueError("missing")
                    return self
            """
        )
    )
    expected = RaiseCount(0)
    assert RaiseCheck.count(source, TyperBoundary(False)) == expected


def test_flags_a_raise_in_a_function_with_another_decorator() -> None:
    source = ast.parse(
        dedent(
            """
            class Directory(RootModel[Path]):
                @staticmethod
                def of(path: Path) -> Directory:
                    raise ValueError("missing")
            """
        )
    )
    expected = RaiseCount(1)
    assert RaiseCheck.count(source, TyperBoundary(False)) == expected


def test_allows_typer_exceptions_at_the_typer_boundary() -> None:
    source = ast.parse(
        dedent(
            """
            def drain() -> None:
                raise typer.BadParameter("--dry-run cannot be combined with --watch.")
                raise typer.Exit(code=1)
            """
        )
    )
    expected = RaiseCount(0)
    assert RaiseCheck.count(source, TyperBoundary(True)) == expected


def test_flags_typer_exceptions_outside_the_typer_boundary() -> None:
    source = ast.parse(
        dedent(
            """
            def drain() -> None:
                raise typer.Exit(code=1)
            """
        )
    )
    expected = RaiseCount(1)
    assert RaiseCheck.count(source, TyperBoundary(False)) == expected


def test_allows_system_exit() -> None:
    source = ast.parse(
        dedent(
            """
            def handle(number: int) -> None:
                raise SystemExit(128 + number)
            """
        )
    )
    expected = RaiseCount(0)
    assert RaiseCheck.count(source, TyperBoundary(False)) == expected


def test_a_scan_counts_raises_per_dotted_module(tmp_path: Path) -> None:
    (tmp_path / "app/core").mkdir(parents=True)
    _ = (tmp_path / "app/core/parse.py").write_text('raise ValueError("unreadable")\n')
    _ = (tmp_path / "app/__init__.py").write_text('raise ValueError("unreadable")\n')
    _ = (tmp_path / "app/clean.py").write_text("x = 1\n")
    expected = RaiseCounts(
        {ModuleName("app.core.parse"): RaiseCount(1), ModuleName("app"): RaiseCount(1)}
    )
    assert RaiseCheck.scan(ExistingDirectory(tmp_path), ModuleName("app.cli")) == expected


def test_a_scan_treats_the_typer_package_and_its_modules_as_the_boundary(tmp_path: Path) -> None:
    (tmp_path / "app/cli").mkdir(parents=True)
    for module in ("app/cli/__init__.py", "app/cli/ticket.py", "app/client.py"):
        _ = (tmp_path / module).write_text("raise typer.Exit(code=0)\n")
    expected = RaiseCounts({ModuleName("app.client"): RaiseCount(1)})
    assert RaiseCheck.scan(ExistingDirectory(tmp_path), ModuleName("app.cli")) == expected


def baseline_of(directory: BaselineDirectory, counts: RaiseCounts) -> RaiseBaseline:
    baseline = RaiseBaseline(directory)
    for module, count in counts.root.items():
        baseline.record(module, count)
    return baseline


def test_a_count_above_the_baseline_is_an_overrun(tmp_path: Path) -> None:
    baseline_count, found_count = RaiseCount(1), RaiseCount(2)
    baseline = baseline_of(
        BaselineDirectory(tmp_path), RaiseCounts({ModuleName.fake(): baseline_count})
    )
    overruns = baseline.burn_down(RaiseCounts({ModuleName.fake(): found_count}))
    assert overruns == (
        Overrun(module=ModuleName.fake(), baseline=baseline_count, found=found_count),
    )


def test_an_overrun_leaves_the_baseline_as_it_was(tmp_path: Path) -> None:
    before = RaiseCounts({ModuleName.fake(): RaiseCount(1)})
    baseline = baseline_of(BaselineDirectory(tmp_path), before)
    _ = baseline.burn_down(RaiseCounts({ModuleName.fake(): RaiseCount(2)}))
    assert baseline.counts() == before


def test_raises_in_a_module_missing_from_the_baseline_are_an_overrun(tmp_path: Path) -> None:
    found_count = RaiseCount(1)
    baseline = baseline_of(BaselineDirectory(tmp_path), RaiseCounts({}))
    overruns = baseline.burn_down(RaiseCounts({ModuleName.fake(): found_count}))
    assert overruns == (
        Overrun(module=ModuleName.fake(), baseline=RaiseCount(0), found=found_count),
    )


def test_a_count_at_the_baseline_passes_and_keeps_it(tmp_path: Path) -> None:
    counts = RaiseCounts({ModuleName.fake(): RaiseCount(2)})
    baseline = baseline_of(BaselineDirectory(tmp_path), counts)
    assert baseline.burn_down(counts) == ()
    assert baseline.counts() == counts


def test_a_count_below_the_baseline_lowers_it(tmp_path: Path) -> None:
    lowered = RaiseCounts({ModuleName.fake(): RaiseCount(1)})
    baseline = baseline_of(
        BaselineDirectory(tmp_path), RaiseCounts({ModuleName.fake(): RaiseCount(3)})
    )
    assert baseline.burn_down(lowered) == ()
    assert baseline.counts() == lowered


def test_a_clean_module_loses_its_baseline_file(tmp_path: Path) -> None:
    directory = BaselineDirectory(tmp_path / "raise-baseline")
    baseline = RaiseBaseline(directory)
    baseline.record(ModuleName.fake(), RaiseCount(2))
    assert baseline.burn_down(RaiseCounts({})) == ()
    assert list(directory.root.iterdir()) == []


def test_each_module_keeps_its_own_baseline_file(tmp_path: Path) -> None:
    other = ModuleName("app.other")
    counts = RaiseCounts({ModuleName.fake(): RaiseCount(1), other: RaiseCount(4)})
    directory = BaselineDirectory(tmp_path)
    _ = baseline_of(directory, counts)
    assert len(list(directory.root.iterdir())) == len(counts.root)


def test_no_module_raises_more_than_its_baseline() -> None:
    source_root = Path(__file__).parents[2]
    baseline = RaiseBaseline(BaselineDirectory(source_root.parent / "raise-baseline"))
    found = RaiseCheck.scan(
        ExistingDirectory(source_root), ModuleName("mb_workflow.a_presentation.cli")
    )
    overruns = baseline.burn_down(found)
    assert overruns == (), "\n".join(OverrunReport.of(overrun).root for overrun in overruns)
