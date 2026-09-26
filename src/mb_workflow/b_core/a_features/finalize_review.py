import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManager
    from mb_workflow.b_core.d_domain_model.pull_request import PrNumber
    from mb_workflow.b_core.d_domain_model.workspace import WorkspaceStatus, Worktree
    from mb_workflow.c_infrastructure.github import GitHub, ReviewRequest

logger = logging.getLogger(__name__)


class NotFinalizableError(Exception):
    pass


def reviewed_pr(worktree: Worktree, status: WorkspaceStatus) -> PrNumber:
    found = worktree.status
    if found is None or found != status:
        raise NotFinalizableError(
            f"{worktree.path.root} is in status "
            f"{found.root if found is not None else 'none'}, expected {status.root}"
        )
    if worktree.pull_request is None:
        raise NotFinalizableError(f"{worktree.path.root} has no linked pull request")
    return worktree.pull_request


def finalize(
    github: GitHub, manager: WorkspaceManager, request: ReviewRequest, status: WorkspaceStatus
) -> None:
    if request.decision.body_required.root and len(request.body.root) == 0:
        raise NotFinalizableError(f"{request.decision.flag.root} requires comment text")

    worktree = manager.current()
    pr = reviewed_pr(worktree, status)
    github.review(pr, request)
    logger.info("Submitted %s on PR #%s.", request.decision.flag.root, pr.root)

    manager.remove(worktree.path)
    logger.info("Removed %s.", worktree.path.root)
