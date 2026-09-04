import logging

import typer

from mb_workflow.greeting import Greeting, PersonName
from mb_workflow.logging import LogLevel, configure

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main(quiet: bool = typer.Option(False, "--quiet", "-q")) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))


@app.command()
def greet(name: str = typer.Argument("Ada")) -> None:
    typer.echo(Greeting.to(PersonName(name)).root)
