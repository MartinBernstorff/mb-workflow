from typer.testing import CliRunner

from mb_workflow.a_presentation.cli import app, flow_app
from mb_workflow.b_core.d_domain_model.flow import EventNames, WorkflowChart


def test_a_command_exists_for_every_event_the_chart_holds() -> None:
    registered = {command.name for command in flow_app.registered_commands}
    assert {event.root for event in EventNames.of_chart(WorkflowChart).root} <= registered


def test_a_dry_run_cannot_watch() -> None:
    usage_error = 2
    result = CliRunner().invoke(app, ["workspace", "drain", "--dry-run", "--watch"])
    assert result.exit_code == usage_error


def test_a_command_run_without_its_required_arguments_shows_its_help() -> None:
    command_with_required_argument = ["ticket", "view"]
    usage = "root ticket view [OPTIONS] {issue}"
    error = "Missing argument"
    result = CliRunner().invoke(app, command_with_required_argument)
    assert usage in result.output
    assert error not in result.output
