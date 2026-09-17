import logging
from pathlib import Path

import typer

from mb_workflow.finalize_review import finalize
from mb_workflow.github import Lookback, ReviewBody, ReviewDecision, ReviewRequest
from mb_workflow.label import LabelChange, LabelRequest, change_label
from mb_workflow.linear import Assignee, BranchSlug, IssueIdentifier, LabelName
from mb_workflow.lock import LockName, LockPath
from mb_workflow.logging import LogLevel, configure
from mb_workflow.open_issue import OpenRequest, open_issue
from mb_workflow.orca import ProjectSelector, TerminalText, TimeoutMs, WorkspaceStatus
from mb_workflow.review_workspaces import create_workspaces
from mb_workflow.shell import ExistingDirectory, Shell

app = typer.Typer(no_args_is_help=True)
linear_app = typer.Typer(no_args_is_help=True)
app.add_typer(linear_app, name="linear")

REVIEWING = "status-8"


# Typer collapses a single-command app into the root command unless a callback exists.
@app.callback()
def commands() -> None: ...


@app.command("review-workspaces")
def review_workspaces(
    status: str = typer.Option(REVIEWING, "--status"),
    merged_within_days: int = typer.Option(30, "--merged-within-days"),
    lock: str = typer.Option("review-workspaces", "--lock"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    shell = Shell(ExistingDirectory(Path.cwd()))
    raise typer.Exit(
        code=create_workspaces(
            shell,
            WorkspaceStatus(status),
            Lookback(merged_within_days),
            LockPath.of(LockName(lock)),
        ).root
    )


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


@linear_app.command("label")
@linear_app.command("l")
def label(
    name: str = typer.Argument(..., help="Linear label to add to the linked issue."),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    request = LabelRequest(label=LabelName(name), change=LabelChange.add)
    shell = Shell(ExistingDirectory(Path.cwd()))
    raise typer.Exit(code=change_label(shell, request).root)


@linear_app.command("unlabel")
@linear_app.command("ul")
def unlabel(
    name: str = typer.Argument(..., help="Linear label to remove from the linked issue."),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    request = LabelRequest(label=LabelName(name), change=LabelChange.remove)
    shell = Shell(ExistingDirectory(Path.cwd()))
    raise typer.Exit(code=change_label(shell, request).root)


@app.command("open-issue")
@app.command("oi")
def open_linear_issue(
    *,
    branch: str = typer.Option("", "--branch", envvar="LINEAR_ISSUE_BRANCH_NAME"),
    issue: str = typer.Option("", "--issue", envvar="LINEAR_ISSUE_IDENTIFIER"),
    prompt: str = typer.Option("", "--prompt", envvar="LINEAR_PROMPT"),
    project: str = typer.Option("github:flowbasedk/flowbase", "--project"),
    assignee: str = typer.Option("mab@flowbase.io", "--assignee"),
    idle_timeout_ms: int = typer.Option(60000, "--idle-timeout-ms"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    request = OpenRequest(
        project=ProjectSelector(project),
        branch=BranchSlug(branch),
        issue=IssueIdentifier(issue) if issue else None,
        prompt=TerminalText(prompt) if prompt else None,
        assignee=Assignee(assignee),
        idle_timeout=TimeoutMs(idle_timeout_ms),
    )
    shell = Shell(ExistingDirectory(Path.cwd()))
    raise typer.Exit(code=open_issue(shell, request).root)
