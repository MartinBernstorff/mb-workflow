from typing import TYPE_CHECKING

from mb_workflow.b_core.d_domain_model.pull_request import PullRequests
from mb_workflow.b_core.d_domain_model.workspace import Worktrees

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.git import BranchNames
    from mb_workflow.b_core.d_domain_model.workspace import RepoId, WorkspaceStatus, WorktreePath


def uncovered(prs: PullRequests, worktrees: Worktrees) -> PullRequests:
    linked = {w.pull_request for w in worktrees.root if w.pull_request is not None}
    branches = {w.branch.branch() for w in worktrees.root if w.branch is not None}
    return PullRequests(
        tuple(pr for pr in prs.root if pr.number not in linked and pr.branch not in branches)
    )


def stale(
    prs: PullRequests,
    worktrees: Worktrees,
    repo: RepoId,
    status: WorkspaceStatus,
    here: WorktreePath,
) -> Worktrees:
    numbers = {pr.number for pr in prs.root}
    branches = {pr.branch for pr in prs.root}
    return Worktrees(
        tuple(
            worktree
            for worktree in worktrees.without(here).root
            if worktree.repo == repo
            and worktree.status == status
            and worktree.pull_request not in numbers
            and (worktree.branch is None or worktree.branch.branch() not in branches)
        )
    )


def prunable(worktrees: Worktrees, repo: RepoId, here: WorktreePath) -> Worktrees:
    return Worktrees(
        tuple(
            worktree
            for worktree in worktrees.without(here).root
            if worktree.repo == repo and worktree.branch is not None
        )
    )


def on_branches(worktrees: Worktrees, wanted: BranchNames) -> Worktrees:
    return Worktrees(
        tuple(
            worktree
            for worktree in worktrees.root
            if worktree.branch is not None and worktree.branch.branch() in wanted.root
        )
    )


def union(first: Worktrees, second: Worktrees) -> Worktrees:
    return Worktrees(
        (
            *first.root,
            *(worktree for worktree in second.root if first.at(worktree.path) is None),
        )
    )


def obsolete(
    *,
    requested: PullRequests,
    merged: BranchNames,
    worktrees: Worktrees,
    repo: RepoId,
    status: WorkspaceStatus,
    here: WorktreePath,
) -> Worktrees:
    return union(
        stale(requested, worktrees, repo, status, here),
        on_branches(prunable(worktrees, repo, here), merged),
    )
