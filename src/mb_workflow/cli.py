import logging
from pathlib import Path

import typer

from mb_workflow.finalize_review import finalize
from mb_workflow.github import ReviewBody, ReviewDecision, ReviewRequest
from mb_workflow.logging import LogLevel, configure
from mb_workflow.orca import WorkspaceStatus
from mb_workflow.review_workspaces import create_workspaces
from mb_workflow.shell import ExistingDirectory, Shell

app = typer.Typer(no_args_is_help=True)

REVIEWING = "status-8"


# Typer collapses a single-command app into the root command unless a callback exists.
@app.callback()
def commands() -> None: ...


@app.command("review-workspaces")
def review_workspaces(
    status: str = typer.Option(REVIEWING, "--status"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    shell = Shell(ExistingDirectory(Path.cwd()))
    raise typer.Exit(code=create_workspaces(shell, WorkspaceStatus(status)).root)


@app.command("approve")
@app.command("a")
def approve(
    comment: str = typer.Argument("", help="Review body."),
    status: str = typer.Option(REVIEWING, "--status"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    request = ReviewRequest(decision=ReviewDecision.approve(), body=ReviewBody(comment))
    shell = Shell(ExistingDirectory(Path.cwd()))
    raise typer.Exit(code=finalize(shell, request, WorkspaceStatus(status)).root)


@app.command("reject")
@app.command("r")
def reject(
    comment: str = typer.Argument("", help="Review body."),
    status: str = typer.Option(REVIEWING, "--status"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    request = ReviewRequest(decision=ReviewDecision.reject(), body=ReviewBody(comment))
    shell = Shell(ExistingDirectory(Path.cwd()))
    raise typer.Exit(code=finalize(shell, request, WorkspaceStatus(status)).root)


@app.command("comment")
@app.command("c")
def comment(
    comment: str = typer.Argument("", help="Review body."),
    status: str = typer.Option(REVIEWING, "--status"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    request = ReviewRequest(decision=ReviewDecision.comment(), body=ReviewBody(comment))
    shell = Shell(ExistingDirectory(Path.cwd()))
    raise typer.Exit(code=finalize(shell, request, WorkspaceStatus(status)).root)
