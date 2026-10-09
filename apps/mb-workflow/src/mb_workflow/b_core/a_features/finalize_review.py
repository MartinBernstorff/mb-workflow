import logging
from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from mb_workflow.b_core.b_domain_services.review_columns import ReviewColumns

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.code_review import CodeForge, CodeReviewError
    from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import (
        WorkspaceManager,
        WorkspaceManagerError,
    )
    from mb_workflow.b_core.d_domain_model.pull_request import PrNumber, ReviewRequest
    from mb_workflow.b_core.d_domain_model.workspace import WorkspaceStatus, Worktree

logger = logging.getLogger(__name__)


class NotFinalizableError(Exception):
    pass


class FinalizeReview:
    @staticmethod
    def linked_pr(worktree: Worktree) -> Result[PrNumber, NotFinalizableError]:
        if worktree.pull_request is None:
            return Err(NotFinalizableError(f"{worktree.path.root} has no linked pull request"))
        return Ok(worktree.pull_request)

    @staticmethod
    def check_finishing(
        worktree: Worktree, status: WorkspaceStatus
    ) -> Result[None, NotFinalizableError]:
        found = worktree.status
        if found is None or found != status:
            return Err(
                NotFinalizableError(
                    f"{worktree.path.root} is in status "
                    f"{found.root if found is not None else 'none'}, expected {status.root} "
                    f"({ReviewColumns.finishing_state().root})"
                )
            )
        return Ok(None)

    # The pull request is checked before the board, so a worktree with none costs no Orca call.
    @staticmethod
    def finishable_pr(
        worktree: Worktree, board: WorkspaceStatusStore
    ) -> Result[PrNumber, NotFinalizableError | WorkspaceManagerError]:
        match FinalizeReview.linked_pr(worktree):
            case Ok(pr):
                pass
            case Err() as unlinked:
                return unlinked
        match board.status_for(ReviewColumns.finishing_state()):
            case Ok(finishing):
                pass
            case Err() as unmapped:
                return unmapped
        match FinalizeReview.check_finishing(worktree, finishing):
            case Ok():
                return Ok(pr)
            case Err() as misplaced:
                return misplaced

    @staticmethod
    def finalize(
        review: CodeForge,
        manager: WorkspaceManager,
        board: WorkspaceStatusStore,
        request: ReviewRequest,
    ) -> Result[None, NotFinalizableError | CodeReviewError | WorkspaceManagerError]:
        match manager.current():
            case Ok(worktree):
                pass
            case Err() as unread:
                return unread
        match FinalizeReview.finishable_pr(worktree, board):
            case Ok(pr):
                pass
            case Err() as refused:
                return refused
        match review.submit(pr, request):
            case Ok():
                logger.info("Submitted %s on PR #%s.", request.decision.value, pr.root)
            case Err() as refused:
                return refused
        match manager.remove(worktree.path):
            case Ok():
                logger.info("Removed %s.", worktree.path.root)
                return Ok(None)
            case Err() as kept:
                return kept
