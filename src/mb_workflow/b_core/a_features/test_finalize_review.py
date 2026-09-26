from typing import override

import pytest

from mb_workflow.b_core.a_features.finalize_review import (
    NotFinalizableError,
    finalize,
    reviewed_pr,
)
from mb_workflow.b_core.c_secondary_ports.code_review import (
    CodeReviewError,
    Drafted,
    FakeCodeReview,
    SubmittedReview,
)
from mb_workflow.b_core.d_domain_model.pull_request import (
    PrNumber,
    PullRequests,
    ReviewBody,
    ReviewDecision,
    ReviewRequest,
)
from mb_workflow.c_infrastructure.orca import Orca, Workspace, WorkspaceStatus, WorktreePath
from mb_workflow.c_infrastructure.shell import (
    Command,
    CommandOutput,
    CommandRunner,
    ExistingDirectory,
)


class StandingIn(CommandRunner):
    def __init__(self, worktree: Workspace) -> None:
        self._worktree = worktree
        self.removed: list[WorktreePath] = []

    @override
    def cwd(self) -> ExistingDirectory:
        return ExistingDirectory.fake()

    @override
    def at(self, directory: ExistingDirectory) -> StandingIn:
        return self

    @override
    def run(self, command: Command) -> CommandOutput:
        match command.root:
            case ("orca", "--version"):
                return CommandOutput("")
            case ("orca", "worktree", "current", "--json"):
                worktree = self._worktree.model_dump_json(by_alias=True)
                return CommandOutput(f'{{"ok":true,"result":{{"worktree":{worktree}}}}}')
            case ("orca", "worktree", "rm", "--worktree", selector, "--force", "--json"):
                self.removed.append(WorktreePath.model_validate(selector.removeprefix("path:")))
                return CommandOutput('{"ok":true,"result":{}}')
            case _:
                raise AssertionError(f"orca has no answer for {command.root}")


def test_finalizes_a_worktree_in_the_reviewing_status() -> None:
    assert reviewed_pr(Workspace.fake(), WorkspaceStatus.fake()) == PrNumber.fake()


def test_rejects_a_worktree_in_another_status() -> None:
    worktree = Workspace.fake().model_copy(
        update={"workspace_status": WorkspaceStatus("in-progress")}
    )
    with pytest.raises(NotFinalizableError, match="expected status-8"):
        _ = reviewed_pr(worktree, WorkspaceStatus.fake())


def test_rejects_a_worktree_without_a_status() -> None:
    worktree = Workspace.fake().model_copy(update={"workspace_status": None})
    with pytest.raises(NotFinalizableError, match="status none"):
        _ = reviewed_pr(worktree, WorkspaceStatus.fake())


def test_rejects_a_worktree_with_no_linked_pull_request() -> None:
    worktree = Workspace.fake().model_copy(update={"linked_issue": None})
    with pytest.raises(NotFinalizableError, match="no linked pull request"):
        _ = reviewed_pr(worktree, WorkspaceStatus.fake())


def test_submits_the_decision_on_the_linked_pull_request() -> None:
    review = FakeCodeReview(PullRequests.fake())
    finalize(
        review, Orca(StandingIn(Workspace.fake())), ReviewRequest.fake(), WorkspaceStatus.fake()
    )
    assert review.submitted() == (
        SubmittedReview(pr=PrNumber.fake(), request=ReviewRequest.fake(), drafted=Drafted(False)),
    )


def test_removes_the_worktree_once_the_review_is_in() -> None:
    orca = StandingIn(Workspace.fake())
    finalize(
        FakeCodeReview(PullRequests.fake()),
        Orca(orca),
        ReviewRequest.fake(),
        WorkspaceStatus.fake(),
    )
    assert orca.removed == [WorktreePath.fake()]


def test_a_refused_review_keeps_the_worktree() -> None:
    orca = StandingIn(Workspace.fake())
    bare = ReviewRequest(decision=ReviewDecision.comment, body=ReviewBody(""))
    with pytest.raises(CodeReviewError, match="comment requires comment text"):
        finalize(FakeCodeReview(PullRequests.fake()), Orca(orca), bare, WorkspaceStatus.fake())
    assert orca.removed == []


def test_a_worktree_in_another_status_submits_nothing() -> None:
    review = FakeCodeReview(PullRequests.fake())
    elsewhere = Workspace.fake().model_copy(update={"workspace_status": None})
    with pytest.raises(NotFinalizableError):
        finalize(review, Orca(StandingIn(elsewhere)), ReviewRequest.fake(), WorkspaceStatus.fake())
    assert review.submitted() == ()
