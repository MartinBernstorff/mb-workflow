import logging
from typing import TYPE_CHECKING

from mb_workflow.c_infrastructure.github import GitHub
from mb_workflow.c_infrastructure.orca import Orca, WorkspaceStatus, Worktree

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.code_review import CodeReview
    from mb_workflow.b_core.d_domain_model.pull_request import PrNumber
    from mb_workflow.b_core.d_domain_model.review import ReviewRequest
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


def finalize(shell: Shell, request: ReviewRequest, status: WorkspaceStatus) -> None:
    orca = Orca(shell)
    worktree = orca.current()
    submit_linked_review(GitHub(shell), worktree, request, status)
    orca.remove_worktree(worktree.path)
    logger.info("Removed %s.", worktree.path.root)


def submit_linked_review(
    code_review: CodeReview, worktree: Worktree, request: ReviewRequest, status: WorkspaceStatus
) -> None:
    pr = reviewed_pr(worktree, status)
    code_review.submit_review(pr, request)
    logger.info("Submitted %s on PR #%s.", request.decision, pr.root)
