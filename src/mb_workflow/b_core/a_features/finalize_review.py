import logging
from subprocess import CalledProcessError
from typing import TYPE_CHECKING

from mb_workflow.a_presentation.console import ExitCode
from mb_workflow.c_infrastructure.github import GitHub, ReviewRequest
from mb_workflow.c_infrastructure.orca import Orca, OrcaError, WorkspaceStatus, Worktree

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.pull_request import PrNumber
    from mb_workflow.c_infrastructure.shell import Shell

logger = logging.getLogger(__name__)


class NotFinalizableError(Exception):
    pass


def reviewed_pr(worktree: Worktree, status: WorkspaceStatus) -> PrNumber:
    found = worktree.workspace_status
    if found is None or found != status:
        raise NotFinalizableError(
            f"{worktree.path.root} is in status "
            f"{found.root if found is not None else 'none'}, expected {status.root}"
        )
    if worktree.linked_issue is None:
        raise NotFinalizableError(f"{worktree.path.root} has no linked pull request")
    return worktree.linked_issue


def finalize(shell: Shell, request: ReviewRequest, status: WorkspaceStatus) -> ExitCode:
    try:
        return finalized(GitHub(shell), Orca(shell), request, status)
    except FileNotFoundError as error:
        logger.error("%s is not installed or not on PATH.", error.filename)
        return ExitCode(1)
    except (CalledProcessError, OrcaError, NotFinalizableError, ValueError) as error:
        logger.error("%s", error)
        return ExitCode(1)


def finalized(
    github: GitHub, orca: Orca, request: ReviewRequest, status: WorkspaceStatus
) -> ExitCode:
    if request.decision.body_required.root and len(request.body.root) == 0:
        raise NotFinalizableError(f"{request.decision.flag.root} requires comment text")

    worktree = orca.current()
    pr = reviewed_pr(worktree, status)
    github.review(pr, request)
    logger.info("Submitted %s on PR #%s.", request.decision.flag.root, pr.root)

    orca.remove_worktree(worktree.path)
    logger.info("Removed %s.", worktree.path.root)
    return ExitCode(0)
