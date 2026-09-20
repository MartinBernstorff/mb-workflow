import logging
from subprocess import CalledProcessError
from typing import TYPE_CHECKING

from mb_workflow.clock import Today
from mb_workflow.lock import AlreadyRunningError, LockPath
from mb_workflow.models import Model, Value
from mb_workflow.pull_request import PrNumber
from mb_workflow.shell import ExistingDirectory, ExitCode, Shell
from mb_workflow.trackers.github import GitHub, Lookback, MergedSince, PullRequests
from mb_workflow.workspace.orca import (
    Orca,
    OrcaError,
    RepoId,
    WorkspaceStatus,
    WorktreeName,
    WorktreePath,
    Worktrees,
)

if TYPE_CHECKING:
    from mb_workflow.git import BranchNames

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
    path: ExistingDirectory

    @staticmethod
    def fake() -> CreatedWorkspace:
        return CreatedWorkspace(name=WorktreeName.fake(), path=ExistingDirectory.fake())


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

    def exit_code(self) -> ExitCode:
        return ExitCode(1 if len(self.failed) > 0 else 0)


def uncovered(prs: PullRequests, worktrees: Worktrees) -> PullRequests:
    linked = {w.linked_issue for w in worktrees.root if w.linked_issue is not None}
    branches = {w.branch.branch() for w in worktrees.root if w.branch is not None}
    return PullRequests(
        tuple(pr for pr in prs.root if pr.number not in linked and pr.head_ref_name not in branches)
    )


def stale(
    prs: PullRequests,
    worktrees: Worktrees,
    repo: RepoId,
    status: WorkspaceStatus,
    here: ExistingDirectory,
) -> Worktrees:
    numbers = {pr.number for pr in prs.root}
    branches = {pr.head_ref_name for pr in prs.root}
    cwd = here.root.resolve()
    return Worktrees(
        tuple(
            worktree
            for worktree in worktrees.root
            if worktree.repo_id == repo
            and worktree.workspace_status == status
            and worktree.linked_issue not in numbers
            and (worktree.branch is None or worktree.branch.branch() not in branches)
            and worktree.path.root.resolve() != cwd
        )
    )


def prunable(worktrees: Worktrees, repo: RepoId, here: ExistingDirectory) -> Worktrees:
    cwd = here.root.resolve()
    return Worktrees(
        tuple(
            worktree
            for worktree in worktrees.root
            if worktree.repo_id == repo
            and worktree.branch is not None
            and worktree.path.root.resolve() != cwd
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
    known = {worktree.path.root.resolve() for worktree in first.root}
    return Worktrees(
        (
            *first.root,
            *(worktree for worktree in second.root if worktree.path.root.resolve() not in known),
        )
    )


def create_workspaces(
    shell: Shell, status: WorkspaceStatus, lookback: Lookback, lock: LockPath
) -> ExitCode:
    try:
        with lock.held():
            since = MergedSince.of(lookback, Today.now())
            return workspaces_for_review(GitHub(shell), Orca(shell), status, since).exit_code()
    except AlreadyRunningError as error:
        logger.error("%s", error)
        return ExitCode(1)
    except FileNotFoundError as error:
        logger.error("%s is not installed or not on PATH.", error.filename)
        return ExitCode(1)
    except (CalledProcessError, OrcaError) as error:
        logger.error("%s", error)
        return ExitCode(1)


def workspaces_for_review(
    github: GitHub, orca: Orca, status: WorkspaceStatus, since: MergedSince
) -> Outcome:
    worktrees = orca.worktrees()
    here = orca.where()
    repo = worktrees.repo_id_at(here)
    logger.info("Inspecting %s Orca worktrees from %s", len(worktrees.root), here.root)
    requested = github.review_requested()
    logger.info("PRs awaiting your review: %s", len(requested.root))

    created: list[CreatedWorkspace] = []
    removed: list[WorktreePath] = []
    failed: list[Failure] = []

    obsolete = union(
        stale(requested, worktrees, repo, status, here),
        on_branches(prunable(worktrees, repo, here), github.merged_branches(since)),
    )
    logger.info("Obsolete workspaces: %s", len(obsolete.root))

    for worktree in obsolete.root:
        try:
            logger.info("    Removing %s", worktree.path.root)
            orca.remove_worktree(worktree.path)
        except (CalledProcessError, OrcaError, ValueError) as error:
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
            path = orca.create_worktree(repo, pr.number, pr.title, status)
            logger.info("    Checking out into %s", path.root)
            github.checkout(pr.number, path)
        except (CalledProcessError, OrcaError, ValueError) as error:
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
