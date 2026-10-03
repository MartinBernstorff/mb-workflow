from subprocess import CalledProcessError
from typing import TYPE_CHECKING, Protocol

from safe_result import Err, Ok, Result, safe_with

from mb_workflow.b_core.a_features.start import PromptUndeliveredError, TicketStart
from mb_workflow.b_core.a_features.teardown import Teardown
from mb_workflow.b_core.b_domain_services.worktree_reconciliation import obsolete, uncovered
from mb_workflow.b_core.c_secondary_ports.code_review import CodeReviewError
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTrackerError
from mb_workflow.b_core.c_secondary_ports.workspace_manager import (
    WorkspaceManagerError,
    WorkspaceNaming,
)
from mb_workflow.b_core.d_domain_model.outcome import Failed
from mb_workflow.b_core.d_domain_model.pull_request import CheckoutDirectory, PrNumber
from mb_workflow.b_core.d_domain_model.workspace import (
    AgentName,
    DisplayName,
    Submit,
    TerminalText,
    TimeoutMs,
    WorktreeName,
    WorktreePath,
)
from mb_workflow.d_lib.models import Model, Value

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.claims import ClaimRegistry
    from mb_workflow.b_core.c_secondary_ports.code_review import CodeForge
    from mb_workflow.b_core.c_secondary_ports.run_lock import AlreadyRunningError, RunLock
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManager
    from mb_workflow.b_core.d_domain_model.claim import HostName
    from mb_workflow.b_core.d_domain_model.config import ClaimSettings
    from mb_workflow.b_core.d_domain_model.pull_request import (
        MergedSince,
        PullRequest,
        PullRequests,
    )
    from mb_workflow.b_core.d_domain_model.workspace import RepoId, WorkspaceStatus, Worktrees


class FailureReason(Value[str]):
    @staticmethod
    def fake() -> FailureReason:
        return FailureReason("repo_not_found")


class FailureSubject(Value[str]):
    @staticmethod
    def fake() -> FailureSubject:
        return FailureSubject.of_pr(PrNumber.fake())

    @staticmethod
    def of_pr(pr: PrNumber) -> FailureSubject:
        return FailureSubject(f"PR #{pr.root}")

    @staticmethod
    def of_path(path: WorktreePath) -> FailureSubject:
        return FailureSubject(str(path.root))


class Failure(Model):
    subject: FailureSubject
    reason: FailureReason

    @staticmethod
    def fake() -> Failure:
        return Failure(subject=FailureSubject.fake(), reason=FailureReason.fake())


class CreatedWorkspace(Model):
    name: WorktreeName
    path: WorktreePath

    @staticmethod
    def fake() -> CreatedWorkspace:
        return CreatedWorkspace(name=WorktreeName.fake(), path=WorktreePath.fake())


class ReviewPrompt(Model):
    text: TerminalText
    idle_timeout: TimeoutMs

    @staticmethod
    def fake() -> ReviewPrompt:
        return ReviewPrompt(text=TerminalText("/review-mine"), idle_timeout=TimeoutMs.fake())


class Unchanged(Value[bool]):
    @staticmethod
    def fake() -> Unchanged:
        return Unchanged(False)


class Outcome(Model):
    created: tuple[CreatedWorkspace, ...]
    removed: tuple[WorktreePath, ...]
    failed: tuple[Failure, ...]

    @staticmethod
    def fake() -> Outcome:
        return Outcome(created=(CreatedWorkspace.fake(),), removed=(), failed=())

    def unchanged(self) -> Unchanged:
        return Unchanged(
            len(self.created) == 0 and len(self.removed) == 0 and len(self.failed) == 0
        )

    def failed_any(self) -> Failed:
        return Failed(len(self.failed) > 0)


class Narrator(Protocol):
    def inspecting(self, worktrees: Worktrees, here: WorktreePath) -> None: ...

    def awaiting_review(self, prs: PullRequests) -> None: ...

    def found_obsolete(self, worktrees: Worktrees) -> None: ...

    def removing(self, path: WorktreePath) -> None: ...

    def found_uncovered(self, prs: PullRequests) -> None: ...

    def creating(self, pr: PrNumber) -> None: ...

    def checking_out(self, path: WorktreePath) -> None: ...

    def removal_failed(self, failure: Failure) -> None: ...

    def creation_failed(self, failure: Failure) -> None: ...


class ReviewWorkspaces:
    @staticmethod
    def create_workspaces(
        *,
        review: CodeForge,
        manager: WorkspaceManager,
        claims: ClaimRegistry,
        tracker: TicketTracker,
        claim_settings: ClaimSettings,
        host: HostName,
        lock: RunLock,
        narrator: Narrator,
        status: WorkspaceStatus,
        since: MergedSince,
        prompt: ReviewPrompt | None,
    ) -> Result[Outcome, AlreadyRunningError | CodeReviewError]:
        match lock.acquire():
            case Ok(held):
                with held:
                    return ReviewWorkspaces.reconcile_workspaces(
                        review=review,
                        manager=manager,
                        claims=claims,
                        tracker=tracker,
                        claim_settings=claim_settings,
                        host=host,
                        narrator=narrator,
                        status=status,
                        since=since,
                        prompt=prompt,
                    )
            case Err() as refused:
                return refused

    @staticmethod
    def reconcile_workspaces(
        *,
        review: CodeForge,
        manager: WorkspaceManager,
        claims: ClaimRegistry,
        tracker: TicketTracker,
        claim_settings: ClaimSettings,
        host: HostName,
        narrator: Narrator,
        status: WorkspaceStatus,
        since: MergedSince,
        prompt: ReviewPrompt | None,
    ) -> Result[Outcome, CodeReviewError]:
        worktrees = manager.worktrees()
        current = manager.current()
        here = current.path
        repo = current.repo
        narrator.inspecting(worktrees, here)
        match review.review_requested():
            case Ok(requested):
                narrator.awaiting_review(requested)
            case Err() as unlisted:
                return unlisted
        match review.merged_branches(since):
            case Ok(merged):
                pass
            case Err() as unlisted:
                return unlisted

        created: list[CreatedWorkspace] = []
        removed: list[WorktreePath] = []
        failed: list[Failure] = []

        to_remove = obsolete(
            requested=requested,
            merged=merged,
            worktrees=worktrees,
            repo=repo,
            status=status,
            here=here,
        )
        narrator.found_obsolete(to_remove)

        for worktree in to_remove.root:
            try:
                narrator.removing(worktree.path)
                released: Result[None, Exception] = Teardown.release_and_remove(
                    manager=manager,
                    claims=claims,
                    tracker=tracker,
                    claim_settings=claim_settings,
                    worktree=worktree,
                    host=host,
                )
            except (TicketTrackerError, WorkspaceManagerError) as error:
                released = Err(error)
            match released:
                case Ok():
                    removed.append(worktree.path)
                case Err(error):
                    failure = Failure(
                        subject=FailureSubject.of_path(worktree.path),
                        reason=FailureReason(str(error)),
                    )
                    narrator.removal_failed(failure)
                    failed.append(failure)

        missing = uncovered(requested, worktrees)
        narrator.found_uncovered(missing)

        for pr in missing.root:
            match ReviewWorkspaces.create_review_workspace(
                review=review,
                manager=manager,
                narrator=narrator,
                repo=repo,
                pr=pr,
                status=status,
                prompt=prompt,
            ):
                case Ok(workspace):
                    created.append(workspace)
                case Err(error):
                    failure = Failure(
                        subject=FailureSubject.of_pr(pr.number), reason=FailureReason(str(error))
                    )
                    narrator.creation_failed(failure)
                    failed.append(failure)

        return Ok(Outcome(created=tuple(created), removed=tuple(removed), failed=tuple(failed)))

    # The other ports still raise, so their errors become values here, alongside the code review's.
    @staticmethod
    @safe_with(
        CodeReviewError,
        CalledProcessError,
        PromptUndeliveredError,
        WorkspaceManagerError,
        ValueError,
    )
    def create_review_workspace(
        *,
        review: CodeForge,
        manager: WorkspaceManager,
        narrator: Narrator,
        repo: RepoId,
        pr: PullRequest,
        status: WorkspaceStatus,
        prompt: ReviewPrompt | None,
    ) -> CreatedWorkspace:
        narrator.creating(pr.number)
        opened = manager.create_for_review(
            repo, pr.number, status, None if prompt is None else AgentName.claude()
        )
        path = opened.worktree.path
        WorkspaceNaming.set_display_name_or_warn(manager, path, DisplayName.of_pr(pr.title))
        narrator.checking_out(path)
        review.checkout(pr.number, CheckoutDirectory(path.root)).unwrap()
        if prompt is not None:
            TicketStart.send_prompt(manager, opened, prompt.text, prompt.idle_timeout, Submit(True))
        return CreatedWorkspace(name=WorktreeName.of(pr.number), path=path)
