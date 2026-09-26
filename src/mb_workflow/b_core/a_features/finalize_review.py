import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.code_review import CodeForge
    from mb_workflow.b_core.d_domain_model.pull_request import PrNumber, ReviewRequest
    from mb_workflow.c_infrastructure.orca import Orca, Workspace, WorkspaceStatus

logger = logging.getLogger(__name__)


class NotFinalizableError(Exception):
    pass


def reviewed_pr(worktree: Workspace, status: WorkspaceStatus) -> PrNumber:
    found = worktree.workspace_status
    if found is None or found != status:
        raise NotFinalizableError(
            f"{worktree.path.root} is in status "
            f"{found.root if found is not None else 'none'}, expected {status.root}"
        )
    if worktree.linked_issue is None:
        raise NotFinalizableError(f"{worktree.path.root} has no linked pull request")
    return worktree.linked_issue


def finalize(
    review: CodeForge, orca: Orca, request: ReviewRequest, status: WorkspaceStatus
) -> None:
    worktree = orca.current()
    pr = reviewed_pr(worktree, status)
    review.submit(pr, request)
    logger.info("Submitted %s on PR #%s.", request.decision.value, pr.root)

    orca.remove_worktree(worktree.path)
    logger.info("Removed %s.", worktree.path.root)
