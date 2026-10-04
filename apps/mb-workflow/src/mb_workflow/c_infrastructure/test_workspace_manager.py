from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from assertions import Assert

from mb_workflow.b_core.c_secondary_ports.workspace_manager import (
    FakeWorkspaceManager,
    WorkspaceManagerError,
)
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier, IssueTitle
from mb_workflow.b_core.d_domain_model.pull_request import PrNumber, PrTitle
from mb_workflow.b_core.d_domain_model.workspace import (
    Activate,
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
    return Orca.connected(Shell(ExistingDirectory(Path.cwd()))).unwrap()


@pytest.fixture(
    params=[ManagerKind.fake, pytest.param(ManagerKind.orca, marks=pytest.mark.orca_live)]
)
def kind(request: pytest.FixtureRequest) -> ManagerKind:
    return ManagerKind(request.param)


@pytest.fixture
def board(kind: ManagerKind) -> Board:
    if kind == ManagerKind.fake:
        return Board.fake()
    current = live_orca().current().unwrap()
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
    for worktree in orca.worktrees().unwrap().root:
        if worktree.repo == board.repo and worktree.path.root.name.startswith(planted):
            _ = orca.remove(worktree.path).unwrap()


def for_review(manager: WorkspaceManager, board: Board) -> Worktree:
    return (
        manager.create_for_review(board.repo, contract_pr(), WorkspaceStatus.fake(), None)
        .unwrap()
        .worktree
    )


def test_the_current_worktree_is_among_those_listed(
    manager: WorkspaceManager, board: Board
) -> None:
    Assert.that(manager.current().unwrap().path).matches(board.here)
    _ = Assert.that(manager.worktrees().unwrap().at(board.here)).exists()


def test_a_review_worktree_is_listed_with_its_pull_request_and_status(
    manager: WorkspaceManager, board: Board
) -> None:
    created = for_review(manager, board)
    listed = manager.worktrees().unwrap().at(created.path)
    listed = Assert.that(listed).exists()
    Assert.that((listed.repo, listed.pull_request, listed.status)).matches(
        (board.repo, contract_pr(), WorkspaceStatus.fake())
    )


def test_a_review_worktree_is_named_after_its_pull_request(
    manager: WorkspaceManager, board: Board
) -> None:
    prefix = WorktreeName.of(contract_pr()).root
    Assert.that(for_review(manager, board).path.root.name).starts_with(prefix)


def test_creating_in_a_column_the_board_lacks_is_refused(
    manager: WorkspaceManager, board: Board
) -> None:
    refused = manager.create_for_review(board.repo, contract_pr(), board.unlisted(), None)
    _ = Assert.that(refused).is_err(WorkspaceManagerError)


def test_an_issue_worktree_is_linked_to_its_issue(manager: WorkspaceManager, board: Board) -> None:
    opened = manager.create_for_issue(
        board.project,
        contract_name(),
        IssueIdentifier.fake(),
        None,
        None,
        activate=Activate(False),
    ).unwrap()
    listed = manager.worktrees().unwrap().at(opened.worktree.path)
    listed = Assert.that(listed).exists()
    Assert.that(listed.issue).matches(IssueIdentifier.fake())


def test_an_issue_worktree_is_created_in_its_column(
    manager: WorkspaceManager, board: Board
) -> None:
    opened = manager.create_for_issue(
        board.project,
        contract_name(),
        None,
        None,
        board.other_column(),
        activate=Activate(False),
    ).unwrap()
    listed = manager.worktrees().unwrap().at(opened.worktree.path)
    listed = Assert.that(listed).exists()
    Assert.that(listed.status).matches(board.other_column())


def test_creating_an_issue_worktree_in_a_column_the_board_lacks_is_refused(
    manager: WorkspaceManager, board: Board
) -> None:
    refused = manager.create_for_issue(
        board.project, contract_name(), None, None, board.unlisted(), activate=Activate(False)
    )
    _ = Assert.that(refused).is_err(WorkspaceManagerError)


def test_a_worktree_opened_without_an_agent_has_no_terminal(
    manager: WorkspaceManager, board: Board
) -> None:
    opened = manager.create_for_issue(
        board.project, contract_name(), None, None, None, activate=Activate(False)
    ).unwrap()
    Assert.that(opened.terminal).matches(None)


def test_opening_under_an_unknown_project_is_refused(
    manager: WorkspaceManager, board: Board
) -> None:
    refused = manager.create_for_issue(
        ProjectSelector("github:mb-workflow/no-such-project"),
        contract_name(),
        None,
        None,
        None,
        activate=Activate(False),
    )
    _ = Assert.that(refused).is_err(WorkspaceManagerError)


def test_a_taken_name_puts_the_second_worktree_elsewhere(
    manager: WorkspaceManager, board: Board
) -> None:
    first = manager.create_for_issue(
        board.project, contract_name(), None, None, None, activate=Activate(False)
    ).unwrap()
    second = manager.create_for_issue(
        board.project, contract_name(), None, None, None, activate=Activate(False)
    ).unwrap()
    Assert.that(first.worktree.path).not_().matches(second.worktree.path)
    _ = Assert.that(manager.worktrees().unwrap().at(first.worktree.path)).exists()
    _ = Assert.that(manager.worktrees().unwrap().at(second.worktree.path)).exists()


def test_a_removed_worktree_is_no_longer_listed(manager: WorkspaceManager, board: Board) -> None:
    created = for_review(manager, board)
    manager.remove(created.path).unwrap()
    Assert.that(manager.worktrees().unwrap().at(created.path)).matches(None)


def test_removing_an_unknown_worktree_is_refused(manager: WorkspaceManager, board: Board) -> None:
    refused = manager.remove(board.here.sibling(WorktreeName("mw-contract-never-created")))
    _ = Assert.that(refused).is_err(WorkspaceManagerError)


def test_setting_a_status_moves_the_worktree_to_that_column(
    manager: WorkspaceManager, board: Board
) -> None:
    created = for_review(manager, board)
    manager.set_status(created.path, board.other_column()).unwrap()
    listed = manager.worktrees().unwrap().at(created.path)
    listed = Assert.that(listed).exists()
    Assert.that(listed.status).matches(board.other_column())


def test_setting_a_status_the_board_has_no_column_for_is_refused(
    manager: WorkspaceManager, board: Board
) -> None:
    created = for_review(manager, board)
    refused = manager.set_status(created.path, board.unlisted())
    _ = Assert.that(refused).is_err(WorkspaceManagerError)


def test_a_display_name_set_on_a_worktree_is_listed_back(
    manager: WorkspaceManager, board: Board
) -> None:
    opened = manager.create_for_issue(
        board.project, contract_name(), None, None, None, activate=Activate(False)
    ).unwrap()
    manager.set_display_name(opened.worktree.path, DisplayName.of_issue(IssueTitle.fake())).unwrap()
    listed = manager.worktrees().unwrap().at(opened.worktree.path)
    listed = Assert.that(listed).exists()
    Assert.that(listed.display_name).matches(DisplayName.of_issue(IssueTitle.fake()))


def test_setting_a_display_name_on_an_unknown_worktree_is_refused(
    manager: WorkspaceManager, board: Board
) -> None:
    refused = manager.set_display_name(
        board.here.sibling(WorktreeName("mw-contract-never-created")), DisplayName.fake()
    )
    _ = Assert.that(refused).is_err(WorkspaceManagerError)


def test_a_review_worktree_is_listed_with_the_pr_title_as_its_display_name(
    manager: WorkspaceManager, board: Board
) -> None:
    created = for_review(manager, board)
    manager.set_display_name(created.path, DisplayName.of_pr(PrTitle.fake())).unwrap()
    listed = manager.worktrees().unwrap().at(created.path)
    listed = Assert.that(listed).exists()
    Assert.that(listed.display_name).matches(DisplayName.of_pr(PrTitle.fake()))


def test_a_linked_issue_set_on_a_worktree_is_listed_back(
    manager: WorkspaceManager, board: Board
) -> None:
    opened = manager.create_for_issue(
        board.project, contract_name(), None, None, None, activate=Activate(False)
    ).unwrap()
    manager.set_linked_issue(opened.worktree.path, IssueIdentifier.fake()).unwrap()
    listed = manager.worktrees().unwrap().at(opened.worktree.path)
    listed = Assert.that(listed).exists()
    Assert.that(listed.issue).matches(IssueIdentifier.fake())


def test_setting_a_linked_issue_replaces_the_previous_one(
    manager: WorkspaceManager, board: Board
) -> None:
    replacement = IssueIdentifier("MB-9999")
    opened = manager.create_for_issue(
        board.project,
        contract_name(),
        IssueIdentifier.fake(),
        None,
        None,
        activate=Activate(False),
    ).unwrap()
    manager.set_linked_issue(opened.worktree.path, replacement).unwrap()
    listed = manager.worktrees().unwrap().at(opened.worktree.path)
    listed = Assert.that(listed).exists()
    Assert.that(listed.issue).matches(replacement)


def test_setting_a_linked_issue_on_an_unknown_worktree_is_refused(
    manager: WorkspaceManager, board: Board
) -> None:
    refused = manager.set_linked_issue(
        board.here.sibling(WorktreeName("mw-contract-never-created")), IssueIdentifier.fake()
    )
    _ = Assert.that(refused).is_err(WorkspaceManagerError)
