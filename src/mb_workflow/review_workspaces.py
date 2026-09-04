import logging
from subprocess import CalledProcessError

from mb_workflow.github import GitHub, PrNumber, PullRequests
from mb_workflow.models import Model, Value
from mb_workflow.orca import Orca, OrcaError, WorkspaceStatus, Worktrees

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


class Outcome(Model):
    created: tuple[PrNumber, ...]
    failed: tuple[Failure, ...]

    @staticmethod
    def fake() -> Outcome:
        return Outcome(created=(PrNumber.fake(),), failed=())


def uncovered(prs: PullRequests, worktrees: Worktrees) -> PullRequests:
    linked = {w.linked_issue for w in worktrees.root if w.linked_issue is not None}
    branches = {w.branch.branch() for w in worktrees.root if w.branch is not None}
    return PullRequests(
        tuple(pr for pr in prs.root if pr.number not in linked and pr.head_ref_name not in branches)
    )


def create_workspaces(github: GitHub, orca: Orca, status: WorkspaceStatus) -> Outcome:
    worktrees = orca.worktrees()
    repo = worktrees.repo_id_at(orca.where())
    pending = uncovered(github.review_requested(), worktrees)

    if len(pending.root) == 0:
        logger.info("No PRs awaiting review without a workspace.")
        return Outcome(created=(), failed=())

    created: list[PrNumber] = []
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
            logger.info("PR #%s → %s", pr.number.root, path.root)
            created.append(pr.number)

    return Outcome(created=tuple(created), failed=tuple(failed))
