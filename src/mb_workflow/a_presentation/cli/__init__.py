import logging
from pathlib import Path

import typer

from mb_workflow.a_presentation import commands
from mb_workflow.a_presentation.cli.ticket import ticket_app
from mb_workflow.a_presentation.diagram import DiagramPath, diagram
from mb_workflow.b_core.a_features.autolabel import AutolabelRequest, DryRun
from mb_workflow.b_core.a_features.drain import DrainRequest
from mb_workflow.b_core.a_features.label import LabelChange, LabelRequest
from mb_workflow.b_core.a_features.start import StartRequest
from mb_workflow.b_core.a_features.teardown import TeardownRequest
from mb_workflow.b_core.b_domain_services.flow_report import AsJson
from mb_workflow.b_core.b_domain_services.flow_transition import Force
from mb_workflow.b_core.d_domain_model.autolabel import ExcludePattern, Exclusions
from mb_workflow.b_core.d_domain_model.claim import HostName, TakeOver
from mb_workflow.b_core.d_domain_model.clock import Today
from mb_workflow.b_core.d_domain_model.config import ConfigFileName, WorkingDirectory
from mb_workflow.b_core.d_domain_model.flow import EventName
from mb_workflow.b_core.d_domain_model.issue import (
    CreatedAfter,
    CreatedWithin,
    Creator,
    IssueIdentifier,
    LabelName,
)
from mb_workflow.b_core.d_domain_model.pull_request import (
    Lookback,
    MergedSince,
    ReviewBody,
    ReviewDecision,
    ReviewRequest,
)
from mb_workflow.b_core.d_domain_model.workspace import (
    Submit,
    TimeoutMs,
    WorkspaceStatus,
    WorktreeName,
)
from mb_workflow.c_infrastructure.flock import LockName
from mb_workflow.d_lib.logging import LogLevel, configure

app = typer.Typer(no_args_is_help=True)
linear_app = typer.Typer(no_args_is_help=True)
app.add_typer(linear_app, name="linear")
flow_app = typer.Typer(no_args_is_help=True)
app.add_typer(flow_app, name="flow")
app.add_typer(ticket_app, name="ticket")

REVIEWING = "status-8"
FORCING = "Write the target state without checking the event is legal from the current one."


# Typer collapses a single-command app into the root command unless a callback exists.
@app.callback()
def root() -> None: ...


@app.command("review-workspaces")
def review_workspaces(
    status: str = typer.Option(REVIEWING, "--status"),
    merged_within_days: int = typer.Option(30, "--merged-within-days"),
    lock: str = typer.Option("review-workspaces", "--lock"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    since = MergedSince.of(Lookback(merged_within_days), Today.now())
    raise typer.Exit(
        code=commands.review_workspaces(
            WorkspaceStatus(status), since, LockName(lock), HostName.of_machine()
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
    request = ReviewRequest(decision=ReviewDecision.approve, body=ReviewBody(comment))
    raise typer.Exit(code=commands.finalize_review(request, WorkspaceStatus(status)).root)


@app.command("reject")
@app.command("r")
def reject(
    comment: str = typer.Argument("", help="Review body."),
    status: str = typer.Option(REVIEWING, "--status"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    request = ReviewRequest(decision=ReviewDecision.request_changes, body=ReviewBody(comment))
    raise typer.Exit(code=commands.finalize_review(request, WorkspaceStatus(status)).root)


@app.command("comment")
@app.command("c")
def comment(
    comment: str = typer.Argument("", help="Review body."),
    status: str = typer.Option(REVIEWING, "--status"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    request = ReviewRequest(decision=ReviewDecision.comment, body=ReviewBody(comment))
    raise typer.Exit(code=commands.finalize_review(request, WorkspaceStatus(status)).root)


@linear_app.command("label")
@linear_app.command("l")
def label(
    name: str = typer.Argument(..., help="Linear label to add to the linked issue."),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    request = LabelRequest(label=LabelName(name), change=LabelChange.add)
    raise typer.Exit(code=commands.relabel(request).root)


@linear_app.command("unlabel")
@linear_app.command("ul")
def unlabel(
    name: str = typer.Argument(..., help="Linear label to remove from the linked issue."),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    request = LabelRequest(label=LabelName(name), change=LabelChange.remove)
    raise typer.Exit(code=commands.relabel(request).root)


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
    request = AutolabelRequest(
        label=LabelName(name),
        creator=Creator(creator),
        exclusions=Exclusions(
            projects=ExcludePattern(exclude_projects) if exclude_projects else None,
            statuses=ExcludePattern(exclude_statuses) if exclude_statuses else None,
        ),
        dry_run=DryRun(not apply),
    )
    window = CreatedAfter.of(CreatedWithin(created_within_days), Today.now())
    raise typer.Exit(code=commands.linear_autolabel(request, window).root)


@app.command("start")
def start_ticket(
    *,
    ticket: str = typer.Argument(..., help="Ticket to start, e.g. MB-33."),
    submit: bool = typer.Option(
        False, "--submit", help="Submit the prompt instead of leaving it typed."
    ),
    idle_timeout_ms: int = typer.Option(60000, "--idle-timeout-ms"),
    force: bool = typer.Option(
        False, "--force", help="Take the claim over from whoever holds the ticket."
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    request = StartRequest(
        ticket=IssueIdentifier(ticket),
        submit=Submit(submit),
        idle_timeout=TimeoutMs(idle_timeout_ms),
        host=HostName.of_machine(),
        take_over=TakeOver(force),
    )
    raise typer.Exit(
        code=commands.ticket_start(
            request, WorkingDirectory(Path.cwd()), ConfigFileName.default()
        ).root
    )


@app.command("drain")
def drain(
    *,
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print the tickets the limits allow, in pick order, and start none.",
    ),
    idle_timeout_ms: int = typer.Option(60000, "--idle-timeout-ms"),
    lock: str = typer.Option(
        "drain", "--lock", help="Name of the lock that keeps passes from overlapping."
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Start ready tickets in pick order until a pool limit is reached."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    request = DrainRequest(
        dry_run=DryRun(dry_run),
        idle_timeout=TimeoutMs(idle_timeout_ms),
        host=HostName.of_machine(),
    )
    raise typer.Exit(
        code=commands.drain(
            request, LockName(lock), WorkingDirectory(Path.cwd()), ConfigFileName.default()
        ).root
    )


@app.command("teardown")
def teardown(
    worktree: str = typer.Argument(..., help="Worktree to tear down, e.g. MB-35."),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Release the worktree's claim on its ticket, then remove the worktree."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    request = TeardownRequest(worktree=WorktreeName(worktree), host=HostName.of_machine())
    raise typer.Exit(
        code=commands.teardown(request, WorkingDirectory(Path.cwd()), ConfigFileName.default()).root
    )


@app.command("unclaim")
def unclaim_ticket(
    ticket: str = typer.Argument(..., help="Ticket whose stuck claim to release, e.g. MB-36."),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=commands.ticket_unclaim(IssueIdentifier(ticket)).root)


@flow_app.command("config")
def flow_config(quiet: bool = typer.Option(False, "--quiet", "-q")) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(
        code=commands.flow_config(WorkingDirectory(Path.cwd()), ConfigFileName.default()).root
    )


@flow_app.command("diagram")
def flow_diagram(
    output: str = typer.Option(
        "",
        "--output",
        "-o",
        help="Write the chart here; .md writes a fenced mermaid state diagram, any other extension picks the image format. Prints the mermaid diagram when omitted.",
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
    raise typer.Exit(code=commands.flow_show(AsJson(as_json)).root)


@flow_app.command("seed-labels")
def flow_seed_labels(quiet: bool = typer.Option(False, "--quiet", "-q")) -> None:
    """Create the flow label group in Linear, with one label per flow state."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=commands.flow_seed_labels().root)


@flow_app.command("grill")
def flow_grill(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(
        code=commands.flow_event(
            EventName("grill"),
            Force(force),
            WorkingDirectory(Path.cwd()),
            ConfigFileName.default(),
        ).root
    )


@flow_app.command("to-ticket")
def flow_to_ticket(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(
        code=commands.flow_event(
            EventName("to-ticket"),
            Force(force),
            WorkingDirectory(Path.cwd()),
            ConfigFileName.default(),
        ).root
    )


@flow_app.command("specced")
def flow_specced(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(
        code=commands.flow_event(
            EventName("specced"),
            Force(force),
            WorkingDirectory(Path.cwd()),
            ConfigFileName.default(),
        ).root
    )


@flow_app.command("implement")
def flow_implement(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(
        code=commands.flow_event(
            EventName("implement"),
            Force(force),
            WorkingDirectory(Path.cwd()),
            ConfigFileName.default(),
        ).root
    )


@flow_app.command("qa")
def flow_qa(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(
        code=commands.flow_event(
            EventName("qa"),
            Force(force),
            WorkingDirectory(Path.cwd()),
            ConfigFileName.default(),
        ).root
    )


@flow_app.command("ready")
def flow_ready(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(
        code=commands.flow_event(
            EventName("ready"),
            Force(force),
            WorkingDirectory(Path.cwd()),
            ConfigFileName.default(),
        ).root
    )


@flow_app.command("merge")
def flow_merge(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(
        code=commands.flow_event(
            EventName("merge"),
            Force(force),
            WorkingDirectory(Path.cwd()),
            ConfigFileName.default(),
        ).root
    )


@flow_app.command("merged")
def flow_merged(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(
        code=commands.flow_event(
            EventName("merged"),
            Force(force),
            WorkingDirectory(Path.cwd()),
            ConfigFileName.default(),
        ).root
    )


@flow_app.command("resolve-review")
def flow_resolve_review(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(
        code=commands.flow_event(
            EventName("resolve-review"),
            Force(force),
            WorkingDirectory(Path.cwd()),
            ConfigFileName.default(),
        ).root
    )
