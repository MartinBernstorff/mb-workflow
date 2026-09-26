from typer.testing import CliRunner

from mb_workflow.a_presentation.cli import flow
from mb_workflow.a_presentation.cli.app import app
from mb_workflow.b_core.d_domain_model.flow import EventNames, WorkflowChart


def test_a_command_exists_for_every_event_the_chart_holds() -> None:
    registered = {command.name for command in flow.app.registered_commands}
    assert {event.root for event in EventNames.of_chart(WorkflowChart).root} <= registered


def test_workspace_commands_sit_at_the_root() -> None:
    assert CliRunner().invoke(app, ["approve", "--help"]).exit_code == 0


def test_tickets_are_edited_under_the_ticket_group() -> None:
    assert CliRunner().invoke(app, ["ticket", "edit", "--help"]).exit_code == 0
