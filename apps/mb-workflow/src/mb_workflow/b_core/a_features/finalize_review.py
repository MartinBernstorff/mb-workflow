import logging
from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.code_review import CodeForge, CodeReviewError
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManager
    from mb_workflow.b_core.d_domain_model.pull_request import PrNumber, ReviewRequest
    from mb_workflow.b_core.d_domain_model.workspace import WorkspaceStatus, Worktree

logger = logging.getLogger(__name__)


class NotFinalizableError(Exception):
    pass


class FinalizeReview:
    @staticmethod
    def reviewed_pr(
        worktree: Worktree, status: WorkspaceStatus
    ) -> Result[PrNumber, NotFinalizableError]:
        found = worktree.status
        if found is None or found != status:
            return Err(
                NotFinalizableError(
                    f"{worktree.path.root} is in status "
                    f"{found.root if found is not None else 'none'}, expected {status.root}"
                )
            )
        if worktree.pull_request is None:
            return Err(NotFinalizableError(f"{worktree.path.root} has no linked pull request"))
        return Ok(worktree.pull_request)

    @staticmethod
    def finalize(
        review: CodeForge,
        manager: WorkspaceManager,
        request: ReviewRequest,
        status: WorkspaceStatus,
    ) -> Result[None, NotFinalizableError | CodeReviewError]:
        worktree = manager.current()
        match FinalizeReview.reviewed_pr(worktree, status):
            case Ok(pr):
                match review.submit(pr, request):
                    case Ok():
                        logger.info("Submitted %s on PR #%s.", request.decision.value, pr.root)
                    case Err() as refused:
                        return refused

                manager.remove(worktree.path)
                logger.info("Removed %s.", worktree.path.root)
                return Ok(None)
            case Err() as refused:
                return refused
