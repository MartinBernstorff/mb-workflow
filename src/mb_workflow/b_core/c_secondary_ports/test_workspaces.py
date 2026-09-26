import pytest

from mb_workflow.b_core.c_secondary_ports.workspaces import FakeWorkspaceManager
from mb_workflow.b_core.d_domain_model.directory import ExistingDirectory
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
from mb_workflow.b_core.d_domain_model.workspace import (
    AgentName,
    ProjectSelector,
    TerminalHandle,
    TerminalText,
    TimeoutMs,
    WorkspaceError,
    WorkspaceStatuses,
    Worktree,
    WorktreeName,
    WorktreePath,
    Worktrees,
)


def manager() -> FakeWorkspaceManager:
    here = ExistingDirectory.fake()
    return FakeWorkspaceManager(
        here,
        WorkspaceStatuses.fake(),
        Worktrees((Worktree.fake().model_copy(update={"path": WorktreePath.of(here)}),)),
    )


def test_an_issue_opens_in_the_repo_of_its_project() -> None:
    opened = manager().create_for_issue(
        ProjectSelector.fake(), WorktreeName("add-widget"), IssueIdentifier.fake(), None
    )
    assert (opened.worktree.repo, opened.worktree.issue) == (
        Worktree.fake().repo,
        IssueIdentifier.fake(),
    )


def test_an_issue_in_an_unknown_project_fails() -> None:
    with pytest.raises(WorkspaceError, match="No repo is known"):
        _ = manager().create_for_issue(
            ProjectSelector("github:someone/else"), WorktreeName("add-widget"), None, None
        )


def test_an_issue_cannot_reuse_a_name_taken_in_its_repo() -> None:
    with pytest.raises(WorkspaceError, match="already exists"):
        _ = manager().create_for_issue(ProjectSelector.fake(), WorktreeName.fake(), None, None)


def test_an_issue_opened_without_an_agent_has_no_terminal() -> None:
    opened = manager().create_for_issue(ProjectSelector.fake(), WorktreeName("x"), None, None)
    assert opened.terminal is None


def test_the_agent_terminal_of_an_opened_issue_takes_text() -> None:
    fake = manager()
    opened = fake.create_for_issue(
        ProjectSelector.fake(), WorktreeName("x"), None, AgentName.fake()
    )
    assert opened.terminal is not None
    fake.wait_for_idle(opened.terminal, TimeoutMs.fake())
    fake.send_text(opened.terminal, TerminalText.fake())


def test_typing_into_an_unknown_terminal_fails() -> None:
    with pytest.raises(WorkspaceError, match="No terminal"):
        manager().send_text(TerminalHandle.fake(), TerminalText.fake())
