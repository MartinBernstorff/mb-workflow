import sys
from pathlib import Path

import typer

from hemolint.a_presentation.commands import Commands
from hemolint.b_core.d_domain_model.baseline import BaselineDirectory

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
    directory: Path = typer.Option(
        Path(".hemolint"), "--dir", help="Directory that holds the baseline."
    ),
) -> None:
    """Read linter output from stdin and compare it to the baseline."""
    if prune and baseline:
        _ = sys.stderr.write("--prune and --baseline cannot be used together.\n")
        raise typer.Exit(code=2)
    working = WorkingDirectory.current()
    if baseline:
        command = Commands.record_baseline
    elif prune:
        command = Commands.prune_baseline
    else:
        command = Commands.check_baseline
    code = command(
        LinterOutput(sys.stdin.read()),
        linter_format,
        working,
        BaselineDirectory(working.root / directory),
    )
    raise typer.Exit(code=code.root)
