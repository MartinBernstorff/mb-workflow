from mb_workflow.cli import flow_app
from mb_workflow.flow import EventNames, WorkflowChart


def test_a_command_exists_for_every_event_the_chart_holds() -> None:
    registered = {command.name for command in flow_app.registered_commands}
    assert {event.root for event in EventNames.of_chart(WorkflowChart).root} <= registered
