import logging
from subprocess import CalledProcessError

from mb_workflow.github import GitHub, PrNumber, PullRequests
from mb_workflow.models import Model, Value
from mb_workflow.orca import Orca, OrcaError, WorkspaceStatus, WorktreeName, Worktrees
from mb_workflow.shell import ExistingDirectory, Shell

logger = logging.getLogger(__name__)


class FailureReason(Value[str]):
    @staticmethod
    def fake() -> FailureReason:
        return FailureReason("repo_not_found")


class Failure(Model):
    pr: PrNumber
    reason: FailureReason

    @staticmethod
    def fake() -> Failure:
        return Failure(pr=PrNumber.fake(), reason=FailureReason.fake())


class ExitCode(Value[int]):
    @staticmethod
    def fake() -> ExitCode:
        return ExitCode(0)


class CreatedWorkspace(Model):
    name: WorktreeName
    path: ExistingDirectory

    @staticmethod
    def fake() -> CreatedWorkspace:
        return CreatedWorkspace(name=WorktreeName.fake(), path=ExistingDirectory.fake())


class Outcome(Model):
    created: tuple[CreatedWorkspace, ...]
    failed: tuple[Failure, ...]

    @staticmethod
    def fake() -> Outcome:
        return Outcome(created=(CreatedWorkspace.fake(),), failed=())

    def report(self) -> None:
        if len(self.created) == 0:
            return
        noun = "workspace" if len(self.created) == 1 else "workspaces"
        logger.info("Created %s %s:", len(self.created), noun)
        for workspace in self.created:
            logger.info("  %s → %s", workspace.name.root, workspace.path.root)

    def exit_code(self) -> ExitCode:
        return ExitCode(1 if len(self.failed) > 0 else 0)


def uncovered(prs: PullRequests, worktrees: Worktrees) -> PullRequests:
    linked = {w.linked_issue for w in worktrees.root if w.linked_issue is not None}
    branches = {w.branch.branch() for w in worktrees.root if w.branch is not None}
    return PullRequests(
        tuple(pr for pr in prs.root if pr.number not in linked and pr.head_ref_name not in branches)
    )


def create_workspaces(shell: Shell, status: WorkspaceStatus) -> ExitCode:
    try:
        return workspaces_for_review(GitHub(shell), Orca(shell), status).exit_code()
    except FileNotFoundError as error:
        logger.error("%s is not installed or not on PATH.", error.filename)
        return ExitCode(1)
    except (CalledProcessError, OrcaError) as error:
        logger.error("%s", error)
        return ExitCode(1)


def workspaces_for_review(github: GitHub, orca: Orca, status: WorkspaceStatus) -> Outcome:
    worktrees = orca.worktrees()
    repo = worktrees.repo_id_at(orca.where())
    pending = uncovered(github.review_requested(), worktrees)

    if len(pending.root) == 0:
        logger.info("No PRs awaiting review without a workspace.")
        return Outcome(created=(), failed=())

    created: list[CreatedWorkspace] = []
    failed: list[Failure] = []
    for pr in pending.root:
        try:
            path = orca.create_worktree(repo, pr)
            github.checkout(pr.number, path)
            orca.set_status(pr.number, status)
        except (CalledProcessError, OrcaError, ValueError) as error:
            logger.error("PR #%s failed: %s", pr.number.root, error)
            failed.append(Failure(pr=pr.number, reason=FailureReason(str(error))))
        else:
            created.append(CreatedWorkspace(name=WorktreeName.of(pr.number), path=path))

    outcome = Outcome(created=tuple(created), failed=tuple(failed))
    outcome.report()
    return outcome
