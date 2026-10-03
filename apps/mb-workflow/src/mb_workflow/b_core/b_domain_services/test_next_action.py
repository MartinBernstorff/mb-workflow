import pytest

from mb_workflow.b_core.b_domain_services.next_action import TicketState, next_action
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


def flow_labelled(state: StateName) -> Issue:
    held = GroupedLabel(group=FlowLabels.fake().group, label=LabelName(state.root))
    return Issue.fake().model_copy(update={"grouped": GroupedLabels((held,))})


def test_a_ticket_with_work_left_is_in_the_state_of_its_flow_label() -> None:
    state = StateName.fake()
    assert (
        TicketState.state_with_work_left(WorkflowChart, FlowLabels.fake(), flow_labelled(state))
        == state
    )


def test_a_ticket_without_a_flow_label_is_refused() -> None:
    unlabelled = Issue.fake().model_copy(update={"grouped": GroupedLabels(())})
    with pytest.raises(FlowError, match="no flow label"):
        _ = TicketState.state_with_work_left(WorkflowChart, FlowLabels.fake(), unlabelled)


def test_a_finished_ticket_is_refused() -> None:
    merged = flow_labelled(StateName("Merged"))
    with pytest.raises(FlowError, match="no work left"):
        _ = TicketState.state_with_work_left(WorkflowChart, FlowLabels.fake(), merged)
