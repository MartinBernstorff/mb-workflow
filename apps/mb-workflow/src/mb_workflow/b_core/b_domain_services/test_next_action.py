import re

import pytest
from safe_result import Err, Ok

from mb_workflow.b_core.b_domain_services.next_action import TicketState
from mb_workflow.b_core.d_domain_model.flow import (
    AwaitingHuman,
    Finished,
    FlowError,
    NextAction,
    Skill,
    StateName,
    WorkflowChart,
)
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
from mb_workflow.b_core.d_domain_model.issue import (
    GroupedLabel,
    GroupedLabels,
    Issue,
    LabelName,
)


@pytest.mark.parametrize(
    ("state", "action"),
    [
        (StateName("grill"), Skill("/grill")),
        (StateName("to-ticket"), Skill("/to-ticket")),
        (StateName("todo"), Skill("/implement")),
        (StateName("implementing"), Skill("/implement")),
        (StateName("qa"), AwaitingHuman()),
        (StateName("review"), AwaitingHuman()),
        (StateName("merging"), Skill("/merge")),
        (StateName("merged"), Finished()),
    ],
)
def test_every_state_leads_to_the_action_the_chart_names_for_it(
    state: StateName, action: NextAction
) -> None:
    assert TicketState.next_action(WorkflowChart, state) == Ok(action)


def test_a_state_outside_the_chart_has_no_action() -> None:
    refused = TicketState.next_action(WorkflowChart, StateName("Marinating"))
    assert isinstance(refused, Err)
    assert isinstance(refused.error, FlowError)
    assert re.search("Marinating is no state of the chart", str(refused.error))


def flow_labelled(state: StateName) -> Issue:
    held = GroupedLabel(group=FlowLabels.fake().group, label=LabelName(state.root))
    return Issue.fake().model_copy(update={"grouped": GroupedLabels((held,))})


def test_a_ticket_with_work_left_is_in_the_state_of_its_flow_label() -> None:
    state = StateName.fake()
    assert TicketState.state_with_work_left(
        WorkflowChart, FlowLabels.fake(), flow_labelled(state)
    ) == Ok(state)


def test_a_ticket_without_a_flow_label_is_refused() -> None:
    unlabelled = Issue.fake().model_copy(update={"grouped": GroupedLabels(())})
    refused = TicketState.state_with_work_left(WorkflowChart, FlowLabels.fake(), unlabelled)
    assert isinstance(refused, Err)
    assert isinstance(refused.error, FlowError)
    assert re.search("no flow label", str(refused.error))


def test_a_finished_ticket_is_refused() -> None:
    merged = flow_labelled(StateName("merged"))
    refused = TicketState.state_with_work_left(WorkflowChart, FlowLabels.fake(), merged)
    assert isinstance(refused, Err)
    assert isinstance(refused.error, FlowError)
    assert re.search("no work left", str(refused.error))
