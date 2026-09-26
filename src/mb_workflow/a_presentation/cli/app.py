import typer

from mb_workflow.a_presentation.cli import flow, ticket, workspace

app = typer.Typer(no_args_is_help=True)
app.add_typer(workspace.app)
app.add_typer(ticket.app, name="ticket")
app.add_typer(flow.app, name="flow")


# Typer collapses a single-command app into the root command unless a callback exists.
@app.callback()
def root() -> None: ...
