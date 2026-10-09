from typing import TYPE_CHECKING

from mb_workflow.b_core.d_domain_model.pull_request import PrNumbers, PullRequests
from mb_workflow.b_core.d_domain_model.workspace import Worktrees

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.git import BranchNames
    from mb_workflow.b_core.d_domain_model.workspace import (
        RepoId,
        WorkspaceStatuses,
        WorktreePath,
    )


class WorktreeReconciliation:
    @staticmethod
    def uncovered(prs: PullRequests, worktrees: Worktrees) -> PullRequests:
        linked = {w.pull_request for w in worktrees.root if w.pull_request is not None}
        branches = {w.branch.branch() for w in worktrees.root if w.branch is not None}
        return PullRequests(
            tuple(pr for pr in prs.root if pr.number not in linked and pr.branch not in branches)
        )

    # A review worktree goes stale once its PR no longer awaits review, whichever review column it is in.
    # A worktree linked to a ticket of mine, or to no pull request, is never a review worktree, even
    # when it shares a column with one, as agent-reviewing does. A worktree for a pull request I
    # opened can still land here; `others` drops it.
    @staticmethod
    def stale(
        prs: PullRequests,
        worktrees: Worktrees,
        repo: RepoId,
        statuses: WorkspaceStatuses,
        here: WorktreePath,
    ) -> Worktrees:
        numbers = {pr.number for pr in prs.root}
        branches = {pr.branch for pr in prs.root}
        return Worktrees(
            tuple(
                worktree
                for worktree in worktrees.without(here).root
                if worktree.repo == repo
                and worktree.issue is None
                and worktree.pull_request is not None
                and worktree.status in statuses.root
                and worktree.pull_request not in numbers
                and (worktree.branch is None or worktree.branch.branch() not in branches)
            )
        )

    # Cleanup never removes the worktree of a pull request I opened, whichever column it sits in.
    @staticmethod
    def others(worktrees: Worktrees, mine: PrNumbers) -> Worktrees:
        return Worktrees(
            tuple(worktree for worktree in worktrees.root if worktree.pull_request not in mine.root)
        )

    @staticmethod
    def prunable(worktrees: Worktrees, repo: RepoId, here: WorktreePath) -> Worktrees:
        return Worktrees(
            tuple(
                worktree
                for worktree in worktrees.without(here).root
                if worktree.repo == repo and worktree.branch is not None
            )
        )

    @staticmethod
    def on_branches(worktrees: Worktrees, wanted: BranchNames) -> Worktrees:
        return Worktrees(
            tuple(
                worktree
                for worktree in worktrees.root
                if worktree.branch is not None and worktree.branch.branch() in wanted.root
            )
        )

    @staticmethod
    def union(first: Worktrees, second: Worktrees) -> Worktrees:
        return Worktrees(
            (
                *first.root,
                *(worktree for worktree in second.root if first.at(worktree.path) is None),
            )
        )

    @staticmethod
    def obsolete(
        *,
        stale: Worktrees,
        mine: PrNumbers,
        merged: BranchNames,
        worktrees: Worktrees,
        repo: RepoId,
        here: WorktreePath,
    ) -> Worktrees:
        return WorktreeReconciliation.union(
            WorktreeReconciliation.others(stale, mine),
            WorktreeReconciliation.on_branches(
                WorktreeReconciliation.prunable(worktrees, repo, here), merged
            ),
        )
