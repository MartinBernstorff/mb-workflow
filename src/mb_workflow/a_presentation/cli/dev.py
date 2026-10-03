import logging

import typer

from mb_workflow.a_presentation import commands
from mb_workflow.a_presentation.cli.group import AlphabeticalGroup
from mb_workflow.d_lib.logging import LogLevel, configure

dev_app = typer.Typer(no_args_is_help=True, cls=AlphabeticalGroup)


@dev_app.command("setup")
def dev_setup(quiet: bool = typer.Option(False, "--quiet", "-q")) -> None:
    """Install the dependencies and git hooks a new developer needs in this repo."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=commands.dev_setup().root)
