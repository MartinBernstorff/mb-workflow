import logging
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from mb_workflow.a_presentation import commands
from mb_workflow.a_presentation.cli.dev import dev_app
from mb_workflow.a_presentation.cli.group import AlphabeticalGroup
from mb_workflow.a_presentation.cli.ticket import ticket_app
from mb_workflow.a_presentation.diagram import DiagramPath, diagram
from mb_workflow.b_core.a_features.autolabel import DryRun
from mb_workflow.b_core.a_features.drain import DrainRequest
from mb_workflow.b_core.a_features.drain_watch import WatchRequest
from mb_workflow.b_core.a_features.init_config import Overwrite
from mb_workflow.b_core.a_features.review_workspaces import ReviewPrompt
from mb_workflow.b_core.a_features.start import StartRequest
from mb_workflow.b_core.a_features.teardown import TeardownRequest
from mb_workflow.b_core.b_domain_services.flow_report import AsJson
from mb_workflow.b_core.b_domain_services.flow_transition import Force
from mb_workflow.b_core.d_domain_model.claim import HostName, TakeOver
from mb_workflow.b_core.d_domain_model.clock import IntervalSeconds, Today
from mb_workflow.b_core.d_domain_model.config import ConfigFileName, WorkingDirectory
from mb_workflow.b_core.d_domain_model.flow import EventName
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
from mb_workflow.b_core.d_domain_model.pull_request import (
    Lookback,
    MergedSince,
    ReviewBody,
    ReviewDecision,
    ReviewRequest,
)
from mb_workflow.b_core.d_domain_model.workspace import (
    Activate,
    Submit,
    TerminalText,
    TimeoutMs,
    WorkspaceStatus,
    WorktreeName,
)
from mb_workflow.c_infrastructure.flock import LockName
from mb_workflow.d_lib.logging import LogLevel, configure

if TYPE_CHECKING:
    from mb_workflow.a_presentation.console import ExitCode

app = typer.Typer(no_args_is_help=True, cls=AlphabeticalGroup)
config_app = typer.Typer(no_args_is_help=True, cls=AlphabeticalGroup)
app.add_typer(config_app, name="config")
app.add_typer(dev_app, name="dev")
flow_app = typer.Typer(no_args_is_help=True, cls=AlphabeticalGroup)
app.add_typer(flow_app, name="flow")
review_app = typer.Typer(no_args_is_help=True, cls=AlphabeticalGroup)
app.add_typer(review_app, name="review")
app.add_typer(review_app, name="r", hidden=True)
app.add_typer(ticket_app, name="ticket")
workspace_app = typer.Typer(no_args_is_help=True, cls=AlphabeticalGroup)
app.add_typer(workspace_app, name="workspace")

REVIEWING = "status-8"
FORCING = "Write the target state without checking the event is legal from the current one."


@workspace_app.command("create-reviews")
def workspace_create_reviews(
    *,
    prompt: str = typer.Argument(
        "", help="Prompt to submit to a Claude agent in each newly created workspace."
    ),
    status: str = typer.Option(REVIEWING, "--status"),
    merged_within_days: int = typer.Option(30, "--merged-within-days"),
    lock: str = typer.Option("review-workspaces", "--lock"),
    idle_timeout_ms: int = typer.Option(60000, "--idle-timeout-ms"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    since = MergedSince.of(Lookback(merged_within_days), Today.now())
    review_prompt = (
        ReviewPrompt(text=TerminalText(prompt), idle_timeout=TimeoutMs(idle_timeout_ms))
        if prompt
        else None
    )
    raise typer.Exit(
        code=commands.review_workspaces(
            WorkspaceStatus(status), since, LockName(lock), HostName.of_machine(), review_prompt
        ).root
    )


@review_app.command("approve")
@review_app.command("a", hidden=True)
def approve(
    comment: str = typer.Argument("", help="Review body."),
    status: str = typer.Option(REVIEWING, "--status"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    request = ReviewRequest(decision=ReviewDecision.approve, body=ReviewBody(comment))
    raise typer.Exit(code=commands.finalize_review(request, WorkspaceStatus(status)).root)


@review_app.command("reject")
@review_app.command("r", hidden=True)
def reject(
    comment: str = typer.Argument("See comments", help="Review body."),
    status: str = typer.Option(REVIEWING, "--status"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    request = ReviewRequest(decision=ReviewDecision.request_changes, body=ReviewBody(comment))
    raise typer.Exit(code=commands.finalize_review(request, WorkspaceStatus(status)).root)


@review_app.command("comment")
@review_app.command("c", hidden=True)
def comment(
    comment: str = typer.Argument("", help="Review body."),
    status: str = typer.Option(REVIEWING, "--status"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    request = ReviewRequest(decision=ReviewDecision.comment, body=ReviewBody(comment))
    raise typer.Exit(code=commands.finalize_review(request, WorkspaceStatus(status)).root)


@workspace_app.command("start")
def workspace_start(
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
        activate=Activate(True),
    )
    raise typer.Exit(
        code=commands.ticket_start(
            request, WorkingDirectory(Path.cwd()), ConfigFileName.default()
        ).root
    )


@workspace_app.command("drain")
def workspace_drain(
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
    watch: bool = typer.Option(
        False, "--watch", help="Repeat passes until Ctrl-C, re-reading the config each pass."
    ),
    interval_seconds: int = typer.Option(
        30, "--interval-seconds", min=0, help="Seconds to wait after each --watch pass ends."
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Start ready tickets in pick order until a pool limit is reached. Tickets labelled skip-limits ignore the limits."""
    if dry_run and watch:
        raise typer.BadParameter("--dry-run cannot be combined with --watch.")
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    request = DrainRequest(
        dry_run=DryRun(dry_run),
        idle_timeout=TimeoutMs(idle_timeout_ms),
        host=HostName.of_machine(),
    )
    if watch:
        raise typer.Exit(
            code=commands.drain_watch(
                WatchRequest(drain=request, interval=IntervalSeconds(interval_seconds)),
                LockName(lock),
                WorkingDirectory(Path.cwd()),
                ConfigFileName.default(),
            ).root
        )
    raise typer.Exit(
        code=commands.drain(
            request, LockName(lock), WorkingDirectory(Path.cwd()), ConfigFileName.default()
        ).root
    )


@workspace_app.command("teardown")
def workspace_teardown(
    worktree: str | None = typer.Argument(
        None, help="Worktree to tear down, e.g. MB-35. Defaults to the current worktree."
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Delete every claim on the worktree's ticket and its claim label, then remove the worktree."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    request = TeardownRequest(worktree=None if worktree is None else WorktreeName(worktree))
    raise typer.Exit(
        code=commands.teardown(request, WorkingDirectory(Path.cwd()), ConfigFileName.default()).root
    )


@config_app.command("init")
def config_init(
    force: bool = typer.Option(False, "--force", help="Overwrite an existing config file."),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(
        code=commands.init(
            WorkingDirectory(Path.cwd()), ConfigFileName.default(), Overwrite(force)
        ).root
    )


@config_app.command("show")
def config_show(quiet: bool = typer.Option(False, "--quiet", "-q")) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(
        code=commands.config(WorkingDirectory(Path.cwd()), ConfigFileName.default()).root
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


def flow_event(event: EventName, force: Force) -> ExitCode:
    return commands.flow_event(event, force, WorkingDirectory(Path.cwd()), ConfigFileName.default())


@flow_app.command("grill")
def flow_grill(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=flow_event(EventName("grill"), Force(force)).root)


@flow_app.command("to-ticket")
def flow_to_ticket(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=flow_event(EventName("to-ticket"), Force(force)).root)


@flow_app.command("specced")
def flow_specced(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=flow_event(EventName("specced"), Force(force)).root)


@flow_app.command("implement")
def flow_implement(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=flow_event(EventName("implement"), Force(force)).root)


@flow_app.command("qa")
def flow_qa(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=flow_event(EventName("qa"), Force(force)).root)


@flow_app.command("ready")
def flow_ready(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=flow_event(EventName("ready"), Force(force)).root)


@flow_app.command("merge")
def flow_merge(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=flow_event(EventName("merge"), Force(force)).root)


@flow_app.command("merged")
def flow_merged(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=flow_event(EventName("merged"), Force(force)).root)


@flow_app.command("resolve-review")
def flow_resolve_review(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=flow_event(EventName("resolve-review"), Force(force)).root)
