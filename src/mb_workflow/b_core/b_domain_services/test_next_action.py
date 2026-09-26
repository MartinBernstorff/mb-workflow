import pytest

from mb_workflow.b_core.b_domain_services.next_action import next_action, state_of
from mb_workflow.b_core.d_domain_model.flow import (
    AwaitingHuman,
    Finished,
    FlowError,
    NextAction,
    Skill,
    StateName,
    WorkflowChart,
)
from mb_workflow.b_core.d_domain_model.issue import IssueStatusName


@pytest.mark.parametrize(
    ("status", "action"),
    [
        (IssueStatusName("Backlog"), Skill("/grill")),
        (IssueStatusName("Grilling"), Skill("/grill")),
        (IssueStatusName("Speccing"), Skill("/to-ticket")),
        (IssueStatusName("Specced"), Skill("/implement")),
        (IssueStatusName("Implementing"), Skill("/implement")),
        (IssueStatusName("QA"), AwaitingHuman()),
        (IssueStatusName("Review"), AwaitingHuman()),
        (IssueStatusName("Merging"), Skill("/merge")),
        (IssueStatusName("Merged"), Finished()),
    ],
)
def test_every_status_leads_to_the_action_the_chart_names_for_its_state(
    status: IssueStatusName, action: NextAction
) -> None:
    assert next_action(WorkflowChart, state_of(WorkflowChart, status)) == action


def test_a_backlog_issue_starts_where_the_chart_starts() -> None:
    assert state_of(WorkflowChart, IssueStatusName("Backlog")) == StateName("Grilling")


def test_a_status_is_read_as_the_state_of_the_same_name() -> None:
    assert state_of(WorkflowChart, IssueStatusName("Specced")) == StateName("Specced")


@pytest.mark.parametrize("status", [IssueStatusName("Canceled"), IssueStatusName("Duplicate")])
def test_a_closed_status_is_a_clear_error(status: IssueStatusName) -> None:
    with pytest.raises(FlowError, match=f"{status.root}, so there is no work left"):
        _ = state_of(WorkflowChart, status)


def test_a_status_outside_the_chart_is_a_clear_error() -> None:
    with pytest.raises(FlowError, match="Triage is no state of the chart"):
        _ = state_of(WorkflowChart, IssueStatusName("Triage"))


def test_a_state_outside_the_chart_has_no_action() -> None:
    with pytest.raises(FlowError, match="Marinating is no state of the chart"):
        _ = next_action(WorkflowChart, StateName("Marinating"))
