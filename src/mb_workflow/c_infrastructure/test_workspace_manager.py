from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from mb_workflow.b_core.c_secondary_ports.workspace_manager import (
    FakeWorkspaceManager,
    WorkspaceManagerError,
)
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier, IssueTitle
from mb_workflow.b_core.d_domain_model.pull_request import PrNumber, PrTitle
from mb_workflow.b_core.d_domain_model.workspace import (
    DisplayName,
    ProjectSelector,
    RepoId,
    WorkspaceStatus,
    WorkspaceStatuses,
    Worktree,
    WorktreeName,
    WorktreePath,
    Worktrees,
)
from mb_workflow.c_infrastructure.orca import Orca
from mb_workflow.c_infrastructure.shell import ExistingDirectory, Shell
from mb_workflow.d_lib.models import Model

if TYPE_CHECKING:
    from collections.abc import Generator

    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManager


class ManagerKind(StrEnum):
    fake = "fake"
    orca = "orca"


class Board(Model):
    repo: RepoId
    project: ProjectSelector
    here: WorktreePath
    columns: WorkspaceStatuses

    @staticmethod
    def fake() -> Board:
        return Board(
            repo=RepoId.fake(),
            project=ProjectSelector.fake(),
            here=WorktreePath.fake(),
            columns=WorkspaceStatuses.fake(),
        )

    def unlisted(self) -> WorkspaceStatus:
        return WorkspaceStatus("mb-workflow-contract-no-such-column")

    def other_column(self) -> WorkspaceStatus:
        return self.columns.root[1]


def contract_pr() -> PrNumber:
    return PrNumber(99999)


def contract_name() -> WorktreeName:
    return WorktreeName("mw-contract")


def live_orca() -> Orca:
    return Orca(Shell(ExistingDirectory(Path.cwd())))


@pytest.fixture(
    params=[ManagerKind.fake, pytest.param(ManagerKind.orca, marks=pytest.mark.orca_live)]
)
def kind(request: pytest.FixtureRequest) -> ManagerKind:
    return ManagerKind(request.param)


# The live board must hold the fake's columns, and the suite must run from an mb-workflow worktree.
@pytest.fixture
def board(kind: ManagerKind) -> Board:
    if kind == ManagerKind.fake:
        return Board.fake()
    current = live_orca().current()
    return Board(
        repo=current.repo,
        project=ProjectSelector("github:martinbernstorff/mb-workflow"),
        here=current.path,
        columns=WorkspaceStatuses.fake(),
    )


@pytest.fixture
def manager(kind: ManagerKind, board: Board) -> Generator[WorkspaceManager]:
    if kind == ManagerKind.fake:
        yield FakeWorkspaceManager(
            Worktrees((Worktree.bare(board.repo, board.here),)),
            board.here,
            board.columns,
            board.project,
            board.repo,
        )
        return
    orca = live_orca()
    yield orca
    planted = (contract_name().root, WorktreeName.of(contract_pr()).root)
    for worktree in orca.worktrees().root:
        if worktree.repo == board.repo and worktree.path.root.name.startswith(planted):
            orca.remove(worktree.path)


def for_review(manager: WorkspaceManager, board: Board) -> Worktree:
    return manager.create_for_review(
        board.repo, contract_pr(), WorkspaceStatus.fake(), None
    ).worktree


def test_the_current_worktree_is_among_those_listed(
    manager: WorkspaceManager, board: Board
) -> None:
    assert manager.current().path == board.here
    assert manager.worktrees().at(board.here) is not None


def test_a_review_worktree_is_listed_with_its_pull_request_and_status(
    manager: WorkspaceManager, board: Board
) -> None:
    created = for_review(manager, board)
    listed = manager.worktrees().at(created.path)
    assert listed is not None
    assert (listed.repo, listed.pull_request, listed.status) == (
        board.repo,
        contract_pr(),
        WorkspaceStatus.fake(),
    )


def test_a_review_worktree_is_named_after_its_pull_request(
    manager: WorkspaceManager, board: Board
) -> None:
    assert for_review(manager, board).path.root.name.startswith(WorktreeName.of(contract_pr()).root)


def test_creating_in_a_column_the_board_lacks_is_refused(
    manager: WorkspaceManager, board: Board
) -> None:
    with pytest.raises(WorkspaceManagerError):
        _ = manager.create_for_review(board.repo, contract_pr(), board.unlisted(), None)


def test_an_issue_worktree_is_linked_to_its_issue(manager: WorkspaceManager, board: Board) -> None:
    opened = manager.create_for_issue(
        board.project, contract_name(), IssueIdentifier.fake(), None, None
    )
    listed = manager.worktrees().at(opened.worktree.path)
    assert listed is not None
    assert listed.issue == IssueIdentifier.fake()


def test_an_issue_worktree_is_created_in_its_column(
    manager: WorkspaceManager, board: Board
) -> None:
    opened = manager.create_for_issue(
        board.project, contract_name(), None, None, board.other_column()
    )
    listed = manager.worktrees().at(opened.worktree.path)
    assert listed is not None
    assert listed.status == board.other_column()


def test_creating_an_issue_worktree_in_a_column_the_board_lacks_is_refused(
    manager: WorkspaceManager, board: Board
) -> None:
    with pytest.raises(WorkspaceManagerError):
        _ = manager.create_for_issue(board.project, contract_name(), None, None, board.unlisted())


def test_a_worktree_opened_without_an_agent_has_no_terminal(
    manager: WorkspaceManager, board: Board
) -> None:
    assert (
        manager.create_for_issue(board.project, contract_name(), None, None, None).terminal is None
    )


def test_opening_under_an_unknown_project_is_refused(
    manager: WorkspaceManager, board: Board
) -> None:
    with pytest.raises(WorkspaceManagerError):
        _ = manager.create_for_issue(
            ProjectSelector("github:mb-workflow/no-such-project"),
            contract_name(),
            None,
            None,
            None,
        )


def test_a_taken_name_puts_the_second_worktree_elsewhere(
    manager: WorkspaceManager, board: Board
) -> None:
    first = manager.create_for_issue(board.project, contract_name(), None, None, None)
    second = manager.create_for_issue(board.project, contract_name(), None, None, None)
    assert first.worktree.path != second.worktree.path
    assert manager.worktrees().at(first.worktree.path) is not None
    assert manager.worktrees().at(second.worktree.path) is not None


def test_a_removed_worktree_is_no_longer_listed(manager: WorkspaceManager, board: Board) -> None:
    created = for_review(manager, board)
    manager.remove(created.path)
    assert manager.worktrees().at(created.path) is None


def test_removing_an_unknown_worktree_is_refused(manager: WorkspaceManager, board: Board) -> None:
    with pytest.raises(WorkspaceManagerError):
        manager.remove(board.here.sibling(WorktreeName("mw-contract-never-created")))


def test_setting_a_status_moves_the_worktree_to_that_column(
    manager: WorkspaceManager, board: Board
) -> None:
    created = for_review(manager, board)
    manager.set_status(created.path, board.other_column())
    listed = manager.worktrees().at(created.path)
    assert listed is not None
    assert listed.status == board.other_column()


def test_setting_a_status_the_board_has_no_column_for_is_refused(
    manager: WorkspaceManager, board: Board
) -> None:
    created = for_review(manager, board)
    with pytest.raises(WorkspaceManagerError):
        manager.set_status(created.path, board.unlisted())


def test_a_display_name_set_on_a_worktree_is_listed_back(
    manager: WorkspaceManager, board: Board
) -> None:
    opened = manager.create_for_issue(board.project, contract_name(), None, None, None)
    manager.set_display_name(opened.worktree.path, DisplayName.of_issue(IssueTitle.fake()))
    listed = manager.worktrees().at(opened.worktree.path)
    assert listed is not None
    assert listed.display_name == DisplayName.of_issue(IssueTitle.fake())


def test_setting_a_display_name_on_an_unknown_worktree_is_refused(
    manager: WorkspaceManager, board: Board
) -> None:
    with pytest.raises(WorkspaceManagerError):
        manager.set_display_name(
            board.here.sibling(WorktreeName("mw-contract-never-created")), DisplayName.fake()
        )


def test_a_review_worktree_is_listed_with_the_pr_title_as_its_display_name(
    manager: WorkspaceManager, board: Board
) -> None:
    created = for_review(manager, board)
    manager.set_display_name(created.path, DisplayName.of_pr(PrTitle.fake()))
    listed = manager.worktrees().at(created.path)
    assert listed is not None
    assert listed.display_name == DisplayName.of_pr(PrTitle.fake())
