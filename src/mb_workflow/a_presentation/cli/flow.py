import logging
from pathlib import Path

import typer

from mb_workflow.a_presentation import commands
from mb_workflow.a_presentation.diagram import DiagramPath, diagram
from mb_workflow.b_core.b_domain_services.flow_report import AsJson
from mb_workflow.b_core.b_domain_services.flow_transition import Force
from mb_workflow.b_core.d_domain_model.config import ConfigFileName, WorkingDirectory
from mb_workflow.b_core.d_domain_model.flow import EventName
from mb_workflow.d_lib.logging import LogLevel, configure

app = typer.Typer(no_args_is_help=True)

FORCING = "Write the target state without checking the event is legal from the current one."


@app.command("config")
def flow_config(quiet: bool = typer.Option(False, "--quiet", "-q")) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(
        code=commands.flow_config(WorkingDirectory(Path.cwd()), ConfigFileName.default()).root
    )


@app.command("diagram")
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


@app.command("show")
def flow_show(
    as_json: bool = typer.Option(False, "--json"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=commands.flow_show(AsJson(as_json)).root)


@app.command("grill")
def flow_grill(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=commands.flow_event(EventName("grill"), Force(force)).root)


@app.command("to-ticket")
def flow_to_ticket(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=commands.flow_event(EventName("to-ticket"), Force(force)).root)


@app.command("specced")
def flow_specced(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=commands.flow_event(EventName("specced"), Force(force)).root)


@app.command("implement")
def flow_implement(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=commands.flow_event(EventName("implement"), Force(force)).root)


@app.command("qa")
def flow_qa(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=commands.flow_event(EventName("qa"), Force(force)).root)


@app.command("ready")
def flow_ready(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=commands.flow_event(EventName("ready"), Force(force)).root)


@app.command("merge")
def flow_merge(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=commands.flow_event(EventName("merge"), Force(force)).root)


@app.command("merged")
def flow_merged(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=commands.flow_event(EventName("merged"), Force(force)).root)


@app.command("resolve-review")
def flow_resolve_review(
    force: bool = typer.Option(False, "--force", help=FORCING),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    """Move the workspace to the state this event leads to."""
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=commands.flow_event(EventName("resolve-review"), Force(force)).root)
