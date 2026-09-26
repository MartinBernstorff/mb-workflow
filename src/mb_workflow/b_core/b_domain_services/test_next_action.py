import pytest

from mb_workflow.b_core.b_domain_services.next_action import next_action
from mb_workflow.b_core.d_domain_model.flow import (
    AwaitingHuman,
    Finished,
    FlowError,
    NextAction,
    Skill,
    StateName,
    WorkflowChart,
)


@pytest.mark.parametrize(
    ("state", "action"),
    [
        (StateName("Grilling"), Skill("/grill")),
        (StateName("Speccing"), Skill("/to-ticket")),
        (StateName("Specced"), Skill("/implement")),
        (StateName("Implementing"), Skill("/implement")),
        (StateName("QA"), AwaitingHuman()),
        (StateName("Review"), AwaitingHuman()),
        (StateName("Merging"), Skill("/merge")),
        (StateName("Merged"), Finished()),
    ],
)
def test_every_state_leads_to_the_action_the_chart_names_for_it(
    state: StateName, action: NextAction
) -> None:
    assert next_action(WorkflowChart, state) == action


def test_a_state_outside_the_chart_has_no_action() -> None:
    with pytest.raises(FlowError, match="Marinating is no state of the chart"):
        _ = next_action(WorkflowChart, StateName("Marinating"))
