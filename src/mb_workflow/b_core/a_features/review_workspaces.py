import logging
from subprocess import CalledProcessError
from typing import TYPE_CHECKING

from mb_workflow.b_core.c_secondary_ports.code_review import CodeReviewError
from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManagerError
from mb_workflow.b_core.d_domain_model.clock import Today
from mb_workflow.b_core.d_domain_model.outcome import Failed
from mb_workflow.b_core.d_domain_model.pull_request import (
    CheckoutDirectory,
    MergedSince,
    PrNumber,
    PullRequests,
)
from mb_workflow.b_core.d_domain_model.workspace import (
    RepoId,
    WorkspaceStatus,
    WorktreeName,
    WorktreePath,
    Worktrees,
)
from mb_workflow.d_lib.models import Model, Value

if TYPE_CHECKING:
    from mb_workflow.b_core.b_domain_services.lock import LockPath
    from mb_workflow.b_core.c_secondary_ports.code_review import CodeForge
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManager
    from mb_workflow.b_core.d_domain_model.git import BranchNames
    from mb_workflow.b_core.d_domain_model.pull_request import Lookback

logger = logging.getLogger(__name__)


class FailureReason(Value[str]):
    @staticmethod
    def fake() -> FailureReason:
        return FailureReason("repo_not_found")


class FailureSubject(Value[str]):
    @staticmethod
    def fake() -> FailureSubject:
        return FailureSubject.of_pr(PrNumber.fake())

    @staticmethod
    def of_pr(pr: PrNumber) -> FailureSubject:
        return FailureSubject(f"PR #{pr.root}")

    @staticmethod
    def of_path(path: WorktreePath) -> FailureSubject:
        return FailureSubject(str(path.root))


class Failure(Model):
    subject: FailureSubject
    reason: FailureReason

    @staticmethod
    def fake() -> Failure:
        return Failure(subject=FailureSubject.fake(), reason=FailureReason.fake())


class CreatedWorkspace(Model):
    name: WorktreeName
    path: WorktreePath

    @staticmethod
    def fake() -> CreatedWorkspace:
        return CreatedWorkspace(name=WorktreeName.fake(), path=WorktreePath.fake())


class Unchanged(Value[bool]):
    @staticmethod
    def fake() -> Unchanged:
        return Unchanged(False)


class Outcome(Model):
    created: tuple[CreatedWorkspace, ...]
    removed: tuple[WorktreePath, ...]
    failed: tuple[Failure, ...]

    @staticmethod
    def fake() -> Outcome:
        return Outcome(created=(CreatedWorkspace.fake(),), removed=(), failed=())

    def report(self) -> None:
        if len(self.removed) > 0:
            noun = "workspace" if len(self.removed) == 1 else "workspaces"
            logger.info("Removed %s %s:", len(self.removed), noun)
            for path in self.removed:
                logger.info("    %s", path.root)
        if len(self.created) > 0:
            noun = "workspace" if len(self.created) == 1 else "workspaces"
            logger.info("Created %s %s:", len(self.created), noun)
            for workspace in self.created:
                logger.info("    %s → %s", workspace.name.root, workspace.path.root)

    def unchanged(self) -> Unchanged:
        return Unchanged(
            len(self.created) == 0 and len(self.removed) == 0 and len(self.failed) == 0
        )

    def failed_any(self) -> Failed:
        return Failed(len(self.failed) > 0)


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


def create_workspaces(
    review: CodeForge,
    manager: WorkspaceManager,
    status: WorkspaceStatus,
    lookback: Lookback,
    lock: LockPath,
) -> Outcome:
    with lock.held():
        since = MergedSince.of(lookback, Today.now())
        return workspaces_for_review(review, manager, status, since)


def workspaces_for_review(
    review: CodeForge, manager: WorkspaceManager, status: WorkspaceStatus, since: MergedSince
) -> Outcome:
    worktrees = manager.worktrees()
    current = manager.current()
    here = current.path
    repo = current.repo
    logger.info("Inspecting %s worktrees from %s", len(worktrees.root), here.root)
    requested = review.review_requested()
    logger.info("PRs awaiting your review: %s", len(requested.root))

    created: list[CreatedWorkspace] = []
    removed: list[WorktreePath] = []
    failed: list[Failure] = []

    obsolete = union(
        stale(requested, worktrees, repo, status, here),
        on_branches(prunable(worktrees, repo, here), review.merged_branches(since)),
    )
    logger.info("Obsolete workspaces: %s", len(obsolete.root))

    for worktree in obsolete.root:
        try:
            logger.info("    Removing %s", worktree.path.root)
            manager.remove(worktree.path)
        except WorkspaceManagerError as error:
            logger.error("    %s could not be removed: %s", worktree.path.root, error)
            failed.append(
                Failure(
                    subject=FailureSubject.of_path(worktree.path),
                    reason=FailureReason(str(error)),
                )
            )
        else:
            removed.append(worktree.path)

    missing = uncovered(requested, worktrees)
    logger.info("PRs without a workspace: %s", len(missing.root))

    for pr in missing.root:
        logger.info("Processing #%s", pr.number.root)
        try:
            logger.info("    Creating worktree %s", WorktreeName.of(pr.number).root)
            path = manager.create_for_review(repo, pr.number, pr.title, status).path
            logger.info("    Checking out into %s", path.root)
            review.checkout(pr.number, CheckoutDirectory(path.root))
        except (CalledProcessError, CodeReviewError, WorkspaceManagerError, ValueError) as error:
            logger.error("    PR #%s failed: %s", pr.number.root, error)
            failed.append(
                Failure(subject=FailureSubject.of_pr(pr.number), reason=FailureReason(str(error)))
            )
        else:
            created.append(CreatedWorkspace(name=WorktreeName.of(pr.number), path=path))

    outcome = Outcome(created=tuple(created), removed=tuple(removed), failed=tuple(failed))
    if outcome.unchanged().root:
        logger.info("Review workspaces already match the PRs awaiting review")
    outcome.report()
    return outcome
