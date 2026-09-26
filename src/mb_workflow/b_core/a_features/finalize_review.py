import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.code_review import CodeForge
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManager
    from mb_workflow.b_core.d_domain_model.pull_request import PrNumber, ReviewRequest
    from mb_workflow.b_core.d_domain_model.workspace import WorkspaceStatus, Worktree

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
    review: CodeForge, manager: WorkspaceManager, request: ReviewRequest, status: WorkspaceStatus
) -> None:
    worktree = manager.current()
    pr = reviewed_pr(worktree, status)
    review.submit(pr, request)
    logger.info("Submitted %s on PR #%s.", request.decision.value, pr.root)

    manager.remove(worktree.path)
    logger.info("Removed %s.", worktree.path.root)
