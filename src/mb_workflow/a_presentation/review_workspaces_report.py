import logging
from typing import TYPE_CHECKING, override

from mb_workflow.b_core.a_features.review_workspaces import Narrator
from mb_workflow.b_core.d_domain_model.workspace import WorktreeName

if TYPE_CHECKING:
    from mb_workflow.b_core.a_features.review_workspaces import Failure, Outcome
    from mb_workflow.b_core.d_domain_model.pull_request import PrNumber, PullRequests
    from mb_workflow.b_core.d_domain_model.workspace import WorktreePath, Worktrees

logger = logging.getLogger(__name__)


class LoggingNarrator(Narrator):
    @override
    def inspecting(self, worktrees: Worktrees, here: WorktreePath) -> None:
        logger.info("Inspecting %s worktrees from %s", len(worktrees.root), here.root)

    @override
    def awaiting_review(self, prs: PullRequests) -> None:
        logger.info("PRs awaiting your review: %s", len(prs.root))

    @override
    def found_obsolete(self, worktrees: Worktrees) -> None:
        logger.info("Obsolete workspaces: %s", len(worktrees.root))

    @override
    def removing(self, path: WorktreePath) -> None:
        logger.info("    Removing %s", path.root)

    @override
    def found_uncovered(self, prs: PullRequests) -> None:
        logger.info("PRs without a workspace: %s", len(prs.root))

    @override
    def creating(self, pr: PrNumber) -> None:
        logger.info("Processing #%s", pr.root)
        logger.info("    Creating worktree %s", WorktreeName.of(pr).root)

    @override
    def checking_out(self, path: WorktreePath) -> None:
        logger.info("    Checking out into %s", path.root)

    @override
    def removal_failed(self, failure: Failure) -> None:
        logger.error("    %s could not be removed: %s", failure.subject.root, failure.reason.root)

    @override
    def creation_failed(self, failure: Failure) -> None:
        logger.error("    %s failed: %s", failure.subject.root, failure.reason.root)


def log_review_workspaces_outcome(outcome: Outcome) -> None:
    if outcome.unchanged().root:
        logger.info("Review workspaces already match the PRs awaiting review")
    if len(outcome.removed) > 0:
        noun = "workspace" if len(outcome.removed) == 1 else "workspaces"
        logger.info("Removed %s %s:", len(outcome.removed), noun)
        for path in outcome.removed:
            logger.info("    %s", path.root)
    if len(outcome.created) > 0:
        noun = "workspace" if len(outcome.created) == 1 else "workspaces"
        logger.info("Created %s %s:", len(outcome.created), noun)
        for workspace in outcome.created:
            logger.info("    %s → %s", workspace.name.root, workspace.path.root)
