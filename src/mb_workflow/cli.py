import logging
from pathlib import Path

import typer

from mb_workflow.greeting import Greeting, PersonName
from mb_workflow.logging import LogLevel, configure
from mb_workflow.orca import WorkspaceStatus
from mb_workflow.review_workspaces import create_workspaces
from mb_workflow.shell import ExistingDirectory, Shell

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main(quiet: bool = typer.Option(False, "--quiet", "-q")) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))


@app.command()
def greet(name: str = typer.Argument("Ada")) -> None:
    typer.echo(Greeting.to(PersonName(name)).root)


@app.command("review-workspaces")
def review_workspaces(status: str = typer.Option("Me reviewing others", "--status")) -> None:
    shell = Shell(ExistingDirectory(Path.cwd()))
    raise typer.Exit(code=create_workspaces(shell, WorkspaceStatus(status)).root)
