import logging
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from mb_workflow.cache import CacheDirectory
from mb_workflow.clock import Today
from mb_workflow.config import ConfigFileName, WorkingDirectory
from mb_workflow.diagram import DiagramPath, diagram
from mb_workflow.flow import EventName, EventNames
from mb_workflow.issue import BranchSlug, IssueIdentifier
from mb_workflow.lock import LockName, LockPath
from mb_workflow.logging import LogLevel, configure
from mb_workflow.shell import ExistingDirectory, Shell
from mb_workflow.trackers.github import Lookback, ReviewBody, ReviewDecision, ReviewRequest
from mb_workflow.trackers.linear import (
    Assignee,
    CreatedAfter,
    CreatedWithin,
    Creator,
    IssueQuery,
    LabelName,
)
from mb_workflow.workflows.autolabel import (
    Apply,
    AutolabelRequest,
    ExcludePattern,
    Exclusions,
    LedgerPath,
    autolabel,
)
from mb_workflow.workflows.finalize_review import finalize
from mb_workflow.workflows.flow import show as show_config
from mb_workflow.workflows.label import LabelChange, LabelRequest, change_label
from mb_workflow.workflows.open_issue import OpenRequest, open_issue
from mb_workflow.workflows.review_workspaces import create_workspaces
from mb_workflow.workflows.show_flow import AsJson, show_flow
from mb_workflow.workflows.transition import Force, transition
from mb_workflow.workspace.orca import ProjectSelector, TerminalText, TimeoutMs, WorkspaceStatus

if TYPE_CHECKING:
    from collections.abc import Callable

app = typer.Typer(no_args_is_help=True)
linear_app = typer.Typer(no_args_is_help=True)
app.add_typer(linear_app, name="linear")
flow_app = typer.Typer(no_args_is_help=True)
app.add_typer(flow_app, name="flow")

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


@linear_app.command("autolabel")
def linear_autolabel(
    *,
    name: str = typer.Argument(..., help="Linear label to add to the swept issues."),
    creator: str = typer.Option(..., "--creator"),
    exclude_projects: str = typer.Option("", "--exclude-projects"),
    exclude_statuses: str = typer.Option("", "--exclude-statuses"),
    created_within_days: int = typer.Option(30, "--created-within-days"),
    apply: bool = typer.Option(False, "--apply"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    label = LabelName(name)
    request = AutolabelRequest(
        label=label,
        query=IssueQuery(
            creator=Creator(creator),
            created_after=CreatedAfter.of(CreatedWithin(created_within_days), Today.now()),
        ),
        exclusions=Exclusions(
            projects=ExcludePattern(exclude_projects) if exclude_projects else None,
            statuses=ExcludePattern(exclude_statuses) if exclude_statuses else None,
        ),
        apply=Apply(apply),
    )
    shell = Shell(ExistingDirectory(Path.cwd()))
    ledger = LedgerPath.of(CacheDirectory.of_user(), label)
    raise typer.Exit(code=autolabel(shell, request, ledger).root)


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


@flow_app.command("config")
def flow_config(quiet: bool = typer.Option(False, "--quiet", "-q")) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=show_config(WorkingDirectory(Path.cwd()), ConfigFileName.default()).root)


@flow_app.command("diagram")
def flow_diagram(
    output: str = typer.Option(
        "",
        "--output",
        "-o",
        help="Write the chart as an image here; the extension picks the format. Prints a mermaid state diagram when omitted.",
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=diagram(DiagramPath(Path(output)) if output else None).root)


@flow_app.command("show")
def flow_show(
    as_json: bool = typer.Option(False, "--json"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    shell = Shell(ExistingDirectory(Path.cwd()))
    raise typer.Exit(code=show_flow(shell, AsJson(as_json)).root)


def flow_event(event: EventName) -> Callable[..., None]:
    def move(
        force: bool = typer.Option(
            False, "--force", help="Write the target state without checking the event is legal."
        ),
        quiet: bool = typer.Option(False, "--quiet", "-q"),
    ) -> None:
        configure(LogLevel(logging.WARNING if quiet else logging.INFO))
        shell = Shell(ExistingDirectory(Path.cwd()))
        raise typer.Exit(code=transition(shell, event, Force(force)).root)

    return move


for name in EventNames.of_chart().root:
    _ = flow_app.command(name.root, help="Move the workspace to the state this event leads to.")(
        flow_event(name)
    )
