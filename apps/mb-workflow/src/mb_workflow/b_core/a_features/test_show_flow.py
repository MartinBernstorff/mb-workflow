from assertions import Assert
from safe_result import Ok, Result

from mb_workflow.b_core.a_features.show_flow import FlowShow
from mb_workflow.b_core.b_domain_services.flow_report import AsJson, StatusReport
from mb_workflow.b_core.c_secondary_ports.status import FakeStatusStore
from mb_workflow.b_core.c_secondary_ports.workspace_manager import (
    FakeWorkspaceManager,
    WorkspaceManagerError,
)
from mb_workflow.b_core.d_domain_model.flow import StateName
from mb_workflow.b_core.d_domain_model.workspace import Worktree, Worktrees


def shown(worktree: Worktree, state: StateName) -> Result[StatusReport, WorkspaceManagerError]:
    return FlowShow.show_flow(
        FakeWorkspaceManager(Worktrees((worktree,)), worktree.path),
        lambda _: FakeStatusStore(state),
        AsJson(False),
    )


def test_a_review_worktree_lists_the_events_of_the_review_chart() -> None:
    agent_reviewing = StateName("agent-reviewing")
    review = Worktree.fake().model_copy(update={"issue": None})
    Assert.that(shown(review, agent_reviewing)).matches(
        Ok(StatusReport("agent-reviewing\n  reviewed\n"))
    )


def test_a_worktree_for_my_own_ticket_lists_the_events_of_the_workflow_chart() -> None:
    agent_reviewing = StateName("agent-reviewing")
    Assert.that(shown(Worktree.fake(), agent_reviewing)).matches(
        Ok(StatusReport("agent-reviewing\n  grill\n  implement\n  qa\n  to-ticket\n"))
    )
