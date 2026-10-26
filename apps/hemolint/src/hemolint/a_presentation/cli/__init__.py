import sys
from pathlib import Path

import typer

from hemolint.a_presentation.commands import Commands
from hemolint.b_core.d_domain_model.baseline import BaselineDirectory, BaselineMatching

# Typer reads the annotation at runtime to build the --format choices.
from hemolint.b_core.d_domain_model.linter_format import LinterFormat  # noqa: TC001
from hemolint.b_core.d_domain_model.linter_output import LinterOutput
from hemolint.b_core.d_domain_model.violation import WorkingDirectory

app = typer.Typer(no_args_is_help=True)


# A callback keeps `check` a subcommand while it is the only one.
@app.callback()
def hemolint() -> None:
    """Keep new lint violations out while existing ones are fixed over time."""


@app.command("check")
def check(
    linter_format: LinterFormat = typer.Option(
        ..., "--format", help="Format of the linter output read from stdin."
    ),
    baseline: bool = typer.Option(
        False, "--baseline", help="Record every current violation in the baseline."
    ),
    prune: bool = typer.Option(
        False, "--prune", help="Remove fixed violations from the baseline instead of failing."
    ),
    baseline_by: BaselineMatching | None = typer.Option(
        None,
        "--baseline-by",
        help="With --baseline, record each violation by fingerprint, or only count them per "
        "source file. Defaults to fingerprint.",
    ),
    directory: Path = typer.Option(
        Path(".hemolint"), "--dir", help="Directory that holds the baseline."
    ),
) -> None:
    """Read linter output from stdin and compare it to the baseline."""
    if prune and baseline:
        _ = sys.stderr.write("--prune and --baseline cannot be used together.\n")
        raise typer.Exit(code=2)
    if baseline_by is not None and not baseline:
        _ = sys.stderr.write("--baseline-by only applies with --baseline.\n")
        raise typer.Exit(code=2)
    working = WorkingDirectory.current()
    output = LinterOutput(sys.stdin.read())
    store = BaselineDirectory(working.root / directory)
    if baseline:
        code = Commands.record_baseline(
            output, linter_format, working, store, baseline_by or BaselineMatching.by_fingerprint
        )
    elif prune:
        code = Commands.prune_baseline(output, linter_format, working, store)
    else:
        code = Commands.check_baseline(output, linter_format, working, store)
    raise typer.Exit(code=code.root)
