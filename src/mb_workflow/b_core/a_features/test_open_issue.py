import pytest

from mb_workflow.b_core.a_features.open_issue import (
    OpenRequest,
    PromptPrefix,
    UnprefixedStateError,
    issue_state,
    open_workspace,
)
from mb_workflow.b_core.c_secondary_ports.issue_tracker import FakeIssueTracker, TrackedIssue
from mb_workflow.b_core.c_secondary_ports.workspace_manager import (
    FakeWorkspaceManager,
    WorkspaceManagerError,
)
from mb_workflow.b_core.d_domain_model.issue import (
    Assigned,
    Issue,
    IssueIdentifier,
    IssueState,
    LabelNames,
    StatusName,
)
from mb_workflow.b_core.d_domain_model.workspace import (
    TerminalHandle,
    TerminalText,
    WorktreeName,
    WorktreePath,
    Worktrees,
)


def tracking(status: StatusName) -> FakeIssueTracker:
    issue = Issue.fake().model_copy(update={"status": status})
    return FakeIssueTracker(
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


def opening() -> FakeWorkspaceManager:
    return FakeWorkspaceManager(Worktrees.fake(), WorktreePath.fake())


def opened_at() -> WorktreePath:
    return WorktreePath.fake().sibling(WorktreeName("add-widget"))


def test_opens_a_worktree_linked_to_the_issue() -> None:
    manager = opening()
    open_workspace(manager, tracking(StatusName("Todo")), OpenRequest.fake())
    opened = manager.worktrees().at(opened_at())
    assert opened is not None
    assert opened.issue == IssueIdentifier.fake()


def test_types_the_prefixed_prompt_into_the_agent_terminal() -> None:
    manager = opening()
    open_workspace(manager, tracking(StatusName("Todo")), OpenRequest.fake())
    assert manager.typed(TerminalHandle("terminal-1")) == (
        TerminalText(f"/implement {TerminalText.fake().root}"),
    )


def test_assigns_the_issue_it_opens() -> None:
    tracker = tracking(StatusName("Todo"))
    open_workspace(opening(), tracker, OpenRequest.fake())
    assert tracker.read_issue(IssueIdentifier.fake()).assigned == Assigned(True)


def test_without_a_prompt_no_agent_is_launched() -> None:
    manager = opening()
    promptless = OpenRequest.fake().model_copy(update={"prompt": None})
    open_workspace(manager, tracking(StatusName("Todo")), promptless)
    with pytest.raises(WorkspaceManagerError):
        _ = manager.typed(TerminalHandle("terminal-1"))


def test_a_state_with_no_prefix_opens_nothing() -> None:
    manager = opening()
    with pytest.raises(UnprefixedStateError):
        open_workspace(manager, tracking(StatusName("In Progress")), OpenRequest.fake())
    assert manager.worktrees() == Worktrees.fake()
