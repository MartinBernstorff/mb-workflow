import pytest

from mb_workflow.b_core.a_features.open_issue import (
    OpenRequest,
    PromptPrefix,
    UnprefixedStateError,
    issue_state,
    open_workspace,
)
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import FakeTicketTracker, TrackedIssue
from mb_workflow.b_core.c_secondary_ports.workspace_manager import FakeWorkspaceManager
from mb_workflow.b_core.d_domain_model.config import WorkspaceSettings
from mb_workflow.b_core.d_domain_model.issue import (
    Assignee,
    Issue,
    IssueIdentifier,
    IssueState,
    LabelNames,
    StatusName,
)
from mb_workflow.b_core.d_domain_model.workspace import (
    ProjectSelector,
    TerminalText,
    WorktreePath,
    Worktrees,
)


def tracking(status: StatusName) -> FakeTicketTracker:
    issue = Issue.fake().model_copy(update={"status": status})
    return FakeTicketTracker(
        LabelNames.fake(), (TrackedIssue.fake().model_copy(update={"issue": issue}),)
    )


def test_a_backlog_issue_is_grilled() -> None:
    assert PromptPrefix.of(IssueState.backlog) == PromptPrefix("/grill")


def test_a_maturing_issue_becomes_a_ticket() -> None:
    assert PromptPrefix.of(IssueState.maturing) == PromptPrefix("/to-ticket")


def test_a_todo_issue_is_implemented() -> None:
    assert PromptPrefix.of(IssueState.todo) == PromptPrefix("/implement")


def test_a_state_with_no_prefix_is_an_error() -> None:
    with pytest.raises(UnprefixedStateError):
        _ = PromptPrefix.of(IssueState.in_progress)


def test_the_prefix_leads_the_prompt() -> None:
    prefixed = OpenRequest.fake().prefixed(IssueState.todo)
    assert prefixed.prompt == TerminalText(f"/implement {TerminalText.fake().root}")


def test_an_issue_without_a_state_leaves_the_prompt_alone() -> None:
    assert OpenRequest.fake().prefixed(None) == OpenRequest.fake()


def test_no_prompt_means_nothing_to_prefix() -> None:
    promptless = OpenRequest.fake().model_copy(update={"prompt": None})
    assert promptless.prefixed(IssueState.in_progress) == promptless


def test_reads_the_state_off_the_tracked_issue() -> None:
    tracker = tracking(StatusName("Maturing"))
    assert issue_state(tracker, IssueIdentifier.fake()) == IssueState.maturing


def test_an_unrecognised_status_is_no_state_at_all() -> None:
    tracker = tracking(StatusName("Marinating"))
    assert issue_state(tracker, IssueIdentifier.fake()) is None


def test_an_issue_the_tracker_cannot_read_has_no_state() -> None:
    tracker = tracking(StatusName.fake())
    assert issue_state(tracker, IssueIdentifier("E-404")) is None


def test_no_issue_has_no_state() -> None:
    assert issue_state(tracking(StatusName.fake()), None) is None


def test_opens_a_worktree_linked_to_the_issue() -> None:
    manager = FakeWorkspaceManager(Worktrees.fake(), WorktreePath.fake())
    open_workspace(
        manager, tracking(StatusName("Todo")), WorkspaceSettings.fake(), OpenRequest.fake()
    )
    (opened,) = manager.worktrees().without(WorktreePath.fake()).root
    assert opened.issue == IssueIdentifier.fake()


def test_types_the_prefixed_prompt_into_the_agent_terminal() -> None:
    manager = FakeWorkspaceManager(Worktrees.fake(), WorktreePath.fake())
    open_workspace(
        manager, tracking(StatusName("Todo")), WorkspaceSettings.fake(), OpenRequest.fake()
    )
    assert manager.typed_texts() == (TerminalText(f"/implement {TerminalText.fake().root}"),)


def test_without_a_prompt_nothing_is_typed() -> None:
    manager = FakeWorkspaceManager(Worktrees.fake(), WorktreePath.fake())
    promptless = OpenRequest.fake().model_copy(update={"prompt": None})
    open_workspace(manager, tracking(StatusName("Todo")), WorkspaceSettings.fake(), promptless)
    assert manager.typed_texts() == ()


def test_a_state_with_no_prefix_opens_nothing() -> None:
    manager = FakeWorkspaceManager(Worktrees.fake(), WorktreePath.fake())
    with pytest.raises(UnprefixedStateError):
        open_workspace(
            manager,
            tracking(StatusName("In Progress")),
            WorkspaceSettings.fake(),
            OpenRequest.fake(),
        )
    assert manager.worktrees() == Worktrees.fake()


def test_opens_the_worktree_in_the_configured_project() -> None:
    project = ProjectSelector("github:other/project")
    manager = FakeWorkspaceManager(Worktrees.fake(), WorktreePath.fake(), project=project)
    workspace = WorkspaceSettings.fake().model_copy(update={"orca_project": project})
    open_workspace(manager, tracking(StatusName("Todo")), workspace, OpenRequest.fake())
    (opened,) = manager.worktrees().without(WorktreePath.fake()).root
    assert opened.issue == IssueIdentifier.fake()


def test_assigns_the_issue_to_the_configured_assignee() -> None:
    tracker = tracking(StatusName("Todo"))
    manager = FakeWorkspaceManager(Worktrees.fake(), WorktreePath.fake())
    assignee = Assignee("other@flowbase.io")
    workspace = WorkspaceSettings.fake().model_copy(update={"assignee": assignee})
    open_workspace(manager, tracker, workspace, OpenRequest.fake())
    assert tracker.read_issue_detail(IssueIdentifier.fake()).assignee == assignee
