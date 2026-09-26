import secrets
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from mb_workflow.b_core.c_secondary_ports.workspaces import FakeWorkspaceManager, WorkspaceManager
from mb_workflow.b_core.d_domain_model.directory import ExistingDirectory
from mb_workflow.b_core.d_domain_model.pull_request import PrNumber, PrTitle
from mb_workflow.b_core.d_domain_model.workspace import (
    RepoId,
    WorkspaceError,
    WorkspaceStatus,
    WorkspaceStatuses,
    Worktree,
    WorktreePath,
    Worktrees,
)
from mb_workflow.c_infrastructure.board import Columns
from mb_workflow.c_infrastructure.orca import ColumnLabel, Orca
from mb_workflow.c_infrastructure.shell import Shell

if TYPE_CHECKING:
    from collections.abc import Iterator


class Arena:
    def __init__(
        self,
        manager: WorkspaceManager,
        repo: RepoId,
        statuses: tuple[WorkspaceStatus, WorkspaceStatus],
    ) -> None:
        self.manager = manager
        self.repo = repo
        self.status, self.other_status = statuses
        # A PR number no real review workspace carries, so the real board never sees a collision.
        self.pr = PrNumber(900_000 + secrets.randbelow(100_000))

    def create_review_worktree(self) -> WorktreePath:
        return self.manager.create_for_review(self.repo, self.pr, PrTitle.fake(), self.status)

    def clean_up(self) -> None:
        for worktree in self.manager.worktrees().root:
            if worktree.pull_request == self.pr:
                self.manager.remove_worktree(worktree.path)


def fake_arena() -> Arena:
    here = ExistingDirectory.fake()
    statuses = (WorkspaceStatus.fake(), WorkspaceStatus("status-5"))
    return Arena(
        FakeWorkspaceManager(
            here,
            WorkspaceStatuses(frozenset(statuses)),
            Worktrees((Worktree(repo=RepoId.fake(), path=WorktreePath.of(here)),)),
        ),
        RepoId.fake(),
        statuses,
    )


def orca_arena() -> Arena:
    orca = Orca(Shell(ExistingDirectory(Path.cwd())))
    columns = Columns.parse(orca.columns(ColumnLabel.unknown()))
    return Arena(
        orca,
        orca.worktrees().repo_at(orca.where()),
        (columns.root[0].id, columns.root[1].id),
    )


@pytest.fixture(params=[pytest.param("fake"), pytest.param("orca", marks=pytest.mark.orca)])
def arena(request: pytest.FixtureRequest) -> Iterator[Arena]:
    built = fake_arena() if request.param == "fake" else orca_arena()
    yield built
    built.clean_up()


def test_the_current_worktree_is_the_one_you_stand_in(arena: Arena) -> None:
    manager = arena.manager
    assert manager.current().path.resolved() == WorktreePath.of(manager.where()).resolved()


def test_a_created_review_worktree_is_listed_with_its_pr_and_status(arena: Arena) -> None:
    path = arena.create_review_worktree()
    listed = arena.manager.worktrees().at(path)
    assert (listed.repo, listed.pull_request, listed.status) == (
        arena.repo,
        arena.pr,
        arena.status,
    )


def test_a_removed_worktree_is_no_longer_listed(arena: Arena) -> None:
    path = arena.create_review_worktree()
    arena.manager.remove_worktree(path)
    with pytest.raises(WorkspaceError):
        _ = arena.manager.worktrees().at(path)


def test_a_worktree_name_is_unique_within_a_repo(arena: Arena) -> None:
    _ = arena.create_review_worktree()
    with pytest.raises(WorkspaceError):
        _ = arena.create_review_worktree()


def test_removing_an_unknown_path_fails(arena: Arena) -> None:
    with pytest.raises(WorkspaceError):
        arena.manager.remove_worktree(WorktreePath(Path.cwd().parent / f"pr-{arena.pr.root}"))


def test_a_worktree_moves_to_another_status_the_board_has(arena: Arena) -> None:
    path = arena.create_review_worktree()
    arena.manager.set_status(path, arena.other_status)
    assert arena.manager.worktrees().at(path).status == arena.other_status


def test_setting_a_status_the_board_has_no_column_for_fails(arena: Arena) -> None:
    path = arena.create_review_worktree()
    with pytest.raises(WorkspaceError):
        arena.manager.set_status(path, WorkspaceStatus("mb-workflow-has-no-such-column"))
