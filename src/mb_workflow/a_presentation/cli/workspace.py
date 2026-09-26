import logging

import typer

from mb_workflow.a_presentation import commands
from mb_workflow.b_core.a_features.open_issue import OpenRequest
from mb_workflow.b_core.b_domain_services.lock import LockName
from mb_workflow.b_core.d_domain_model.issue import Assignee, BranchSlug, IssueIdentifier
from mb_workflow.c_infrastructure.github import Lookback, ReviewBody, ReviewDecision, ReviewRequest
from mb_workflow.c_infrastructure.orca import (
    ProjectSelector,
    TerminalText,
    TimeoutMs,
    WorkspaceStatus,
)
from mb_workflow.d_lib.logging import LogLevel, configure

app = typer.Typer()

REVIEWING = "status-8"


@app.command("review-workspaces")
def review_workspaces(
    status: str = typer.Option(REVIEWING, "--status"),
    merged_within_days: int = typer.Option(30, "--merged-within-days"),
    lock: str = typer.Option("review-workspaces", "--lock"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(
        code=commands.review_workspaces(
            WorkspaceStatus(status), Lookback(merged_within_days), LockName(lock)
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
    raise typer.Exit(code=commands.finalize_review(request, WorkspaceStatus(status)).root)


@app.command("reject")
@app.command("r")
def reject(
    comment: str = typer.Argument("", help="Review body."),
    status: str = typer.Option(REVIEWING, "--status"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    request = ReviewRequest(decision=ReviewDecision.reject(), body=ReviewBody(comment))
    raise typer.Exit(code=commands.finalize_review(request, WorkspaceStatus(status)).root)


@app.command("comment")
@app.command("c")
def comment(
    comment: str = typer.Argument("", help="Review body."),
    status: str = typer.Option(REVIEWING, "--status"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    request = ReviewRequest(decision=ReviewDecision.comment(), body=ReviewBody(comment))
    raise typer.Exit(code=commands.finalize_review(request, WorkspaceStatus(status)).root)


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
    raise typer.Exit(code=commands.open_linear_issue(request).root)
