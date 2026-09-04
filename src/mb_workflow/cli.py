import logging
from pathlib import Path
from subprocess import CalledProcessError

import typer

from mb_workflow.github import GitHub
from mb_workflow.greeting import Greeting, PersonName
from mb_workflow.logging import LogLevel, configure
from mb_workflow.orca import Orca, OrcaError, WorkspaceStatus
from mb_workflow.review_workspaces import create_workspaces
from mb_workflow.shell import ExistingDirectory, Shell

app = typer.Typer(no_args_is_help=True)
logger = logging.getLogger(__name__)


@app.callback()
def main(quiet: bool = typer.Option(False, "--quiet", "-q")) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))


@app.command()
def greet(name: str = typer.Argument("Ada")) -> None:
    typer.echo(Greeting.to(PersonName(name)).root)


@app.command("review-workspaces")
def review_workspaces(status: str = typer.Option("Me reviewing others", "--status")) -> None:
    shell = Shell(ExistingDirectory(Path.cwd()))
    try:
        outcome = create_workspaces(GitHub(shell), Orca(shell), WorkspaceStatus(status))
    except FileNotFoundError as error:
        logger.error("%s is not installed or not on PATH.", error.filename)
        raise typer.Exit(code=1) from error
    except (CalledProcessError, OrcaError) as error:
        logger.error("%s", error)
        raise typer.Exit(code=1) from error
    if len(outcome.failed) > 0:
        raise typer.Exit(code=1)
