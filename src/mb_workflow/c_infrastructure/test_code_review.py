from typing import TYPE_CHECKING, Protocol, override

import pytest

from mb_workflow.b_core.c_secondary_ports.code_review import (
    Checkout,
    Checkouts,
    CodeReview,
    FakeCodeReview,
    Submission,
    Submissions,
)
from mb_workflow.b_core.d_domain_model.directory import ExistingDirectory
from mb_workflow.b_core.d_domain_model.git import BranchName, BranchNames
from mb_workflow.b_core.d_domain_model.pull_request import (
    MergedSince,
    PrNumber,
    PrTitle,
    PullRequest,
    PullRequests,
)
from mb_workflow.b_core.d_domain_model.review import (
    MissingReviewBodyError,
    PendingReview,
    ReviewBody,
    ReviewDecision,
    ReviewId,
    ReviewRequest,
)
from mb_workflow.c_infrastructure.github import (
    GitHub,
    PullRequestPayload,
    Review,
    ReviewAuthor,
    ReviewEvent,
    ReviewFlag,
    ReviewState,
    UserLogin,
    event_of,
    flag_of,
)
from mb_workflow.c_infrastructure.shell import Command, CommandOutput, Shell
from mb_workflow.d_lib.models import Model

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


class Seed(Model):
    requested: PullRequests = PullRequests(())
    merged: PullRequests = PullRequests(())
    pending: PendingReview | None = None

    @staticmethod
    def fake() -> Seed:
        return Seed(requested=PullRequests.fake(), merged=PullRequests.fake())


class Host(Protocol):
    def code_review(self) -> CodeReview: ...

    def submitted(self) -> Submissions: ...

    def checked_out(self) -> Checkouts: ...


class FakeHost:
    def __init__(self, seed: Seed) -> None:
        self._fake = FakeCodeReview(seed.requested, seed.merged, seed.pending)

    def code_review(self) -> CodeReview:
        return self._fake

    def submitted(self) -> Submissions:
        return self._fake.submitted()

    def checked_out(self) -> Checkouts:
        return self._fake.checked_out()


class Ran(Model):
    command: Command
    cwd: ExistingDirectory


class ScriptedShell(Shell):
    def __init__(
        self, cwd: ExistingDirectory, answer: Callable[[Command], CommandOutput], log: list[Ran]
    ) -> None:
        super().__init__(cwd)
        self._answer = answer
        self._log = log

    @override
    def in_directory(self, directory: ExistingDirectory) -> Shell:
        return ScriptedShell(directory, self._answer, self._log)

    @override
    def run(self, command: Command) -> CommandOutput:
        self._log.append(Ran(command=command, cwd=self.cwd()))
        return self._answer(command)


def listing(prs: PullRequests) -> CommandOutput:
    return CommandOutput(
        "["
        + ",".join(PullRequestPayload.of(pr).model_dump_json(by_alias=True) for pr in prs.root)
        + "]"
    )


class GitHubHost:
    def __init__(self, seed: Seed) -> None:
        self._seed = seed
        self._pending = seed.pending
        self._log: list[Ran] = []
        self._github = GitHub(ScriptedShell(ExistingDirectory.fake(), self._answer, self._log))

    def _answer(self, command: Command) -> CommandOutput:
        match command.root:
            case ("gh", "pr", "list", "--search", _, *_):
                return listing(self._seed.requested)
            case ("gh", "pr", "list", "--state", "merged", *_):
                return listing(self._seed.merged)
            case ("gh", "api", "user", *_):
                return CommandOutput(f"{UserLogin.fake().root}\n")
            case ("gh", "api", "--paginate", "--slurp", path):
                return self._reviews(PrNumber(int(path.split("/")[-2])))
            case ("gh", "api", "--method", "POST", *_):
                self._pending = None
                return CommandOutput("")
            case _:
                return CommandOutput("")

    def _reviews(self, pr: PrNumber) -> CommandOutput:
        if self._pending is None or self._pending.pr != pr:
            return CommandOutput("[[]]")
        review = Review(
            id=self._pending.id,
            state=ReviewState.pending(),
            user=ReviewAuthor(login=UserLogin.fake()),
        )
        return CommandOutput(f"[[{review.model_dump_json(by_alias=True)}]]")

    def code_review(self) -> CodeReview:
        return self._github

    def submitted(self) -> Submissions:
        return Submissions(
            tuple(
                submission
                for ran in self._log
                if (submission := submitted_by(ran.command)) is not None
            )
        )

    def checked_out(self) -> Checkouts:
        return Checkouts(
            tuple(
                Checkout(pr=PrNumber(int(ran.command.root[3])), into=ran.cwd)
                for ran in self._log
                if ran.command.root[:3] == ("gh", "pr", "checkout")
            )
        )


def decision_flagged(flag: ReviewFlag) -> ReviewDecision:
    return next(decision for decision in ReviewDecision if flag_of(decision) == flag)


def decision_evented(event: ReviewEvent) -> ReviewDecision:
    return next(decision for decision in ReviewDecision if event_of(decision) == event)


def submitted_by(command: Command) -> Submission | None:
    match command.root:
        case ("gh", "pr", "review", pr, flag, *rest):
            return Submission(
                pr=PrNumber(int(pr)),
                request=ReviewRequest(
                    decision=decision_flagged(ReviewFlag(flag)),
                    body=ReviewBody(rest[1] if rest else ""),
                ),
                pending=None,
            )
        case ("gh", "api", "--method", "POST", path, "--silent", "-f", event, *rest):
            parts = path.split("/")
            return Submission(
                pr=PrNumber(int(parts[4])),
                request=ReviewRequest(
                    decision=decision_evented(ReviewEvent(event.removeprefix("event="))),
                    body=ReviewBody(rest[1].removeprefix("body=") if rest else ""),
                ),
                pending=ReviewId(int(parts[6])),
            )
        case _:
            return None


pytestmark = pytest.mark.parametrize("host", [FakeHost, GitHubHost], ids=["fake", "github"])


def other_pr_number() -> PrNumber:
    return PrNumber(7)


def test_lists_the_pull_requests_awaiting_review(host: Callable[[Seed], Host]) -> None:
    assert host(Seed.fake()).code_review().review_requested() == PullRequests.fake()


def test_lists_the_branches_of_merged_pull_requests(host: Callable[[Seed], Host]) -> None:
    merged = PullRequests(
        (
            PullRequest(
                number=other_pr_number(), title=PrTitle.fake(), branch=BranchName("feat/other")
            ),
        )
    )
    code_review = host(Seed(merged=merged)).code_review()
    assert code_review.merged_branches(MergedSince.fake()) == BranchNames(
        (BranchName("feat/other"),)
    )


def test_without_a_pending_review_a_fresh_one_is_submitted(host: Callable[[Seed], Host]) -> None:
    subject = host(Seed())
    subject.code_review().submit_review(PrNumber.fake(), ReviewRequest.fake())
    assert subject.submitted() == Submissions.fake()


def test_a_pending_review_is_submitted_rather_than_a_fresh_one(
    host: Callable[[Seed], Host],
) -> None:
    subject = host(Seed(pending=PendingReview.fake()))
    subject.code_review().submit_review(PrNumber.fake(), ReviewRequest.fake())
    assert subject.submitted() == Submissions(
        (Submission.fake().model_copy(update={"pending": ReviewId.fake()}),)
    )


def test_a_pending_review_on_another_pull_request_is_left_alone(
    host: Callable[[Seed], Host],
) -> None:
    subject = host(Seed(pending=PendingReview(pr=other_pr_number(), id=ReviewId.fake())))
    subject.code_review().submit_review(PrNumber.fake(), ReviewRequest.fake())
    assert subject.submitted() == Submissions.fake()


def test_a_submitted_pending_review_is_no_longer_pending(host: Callable[[Seed], Host]) -> None:
    subject = host(Seed(pending=PendingReview.fake()))
    subject.code_review().submit_review(PrNumber.fake(), ReviewRequest.fake())
    subject.code_review().submit_review(PrNumber.fake(), ReviewRequest.fake())
    assert subject.submitted() == Submissions(
        (Submission.fake().model_copy(update={"pending": ReviewId.fake()}), Submission.fake())
    )


@pytest.mark.parametrize("decision", [ReviewDecision.reject, ReviewDecision.comment])
def test_a_decision_that_needs_a_body_is_refused_without_one(
    host: Callable[[Seed], Host], decision: ReviewDecision
) -> None:
    subject = host(Seed())
    with pytest.raises(MissingReviewBodyError, match=f"{decision} requires comment text"):
        subject.code_review().submit_review(
            PrNumber.fake(), ReviewRequest(decision=decision, body=ReviewBody(""))
        )
    assert subject.submitted() == Submissions(())


def test_an_approval_needs_no_body(host: Callable[[Seed], Host]) -> None:
    subject = host(Seed())
    request = ReviewRequest(decision=ReviewDecision.approve, body=ReviewBody(""))
    subject.code_review().submit_review(PrNumber.fake(), request)
    assert subject.submitted() == Submissions(
        (Submission.fake().model_copy(update={"request": request}),)
    )


def test_a_checkout_lands_in_the_directory_it_was_given(
    host: Callable[[Seed], Host], tmp_path: Path
) -> None:
    subject = host(Seed())
    into = ExistingDirectory(tmp_path)
    subject.code_review().checkout(PrNumber.fake(), into)
    assert subject.checked_out() == Checkouts((Checkout(pr=PrNumber.fake(), into=into),))
