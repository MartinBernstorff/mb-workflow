import json
from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, override

import pytest

from mb_workflow.b_core.c_secondary_ports.code_review import (
    CodeReviewError,
    Drafted,
    FakeCodeReview,
    MergedOn,
    MergedPullRequest,
    SubmittedReview,
)
from mb_workflow.b_core.d_domain_model.git import BranchName
from mb_workflow.b_core.d_domain_model.pull_request import (
    CheckoutDirectory,
    MergedSince,
    PrNumber,
    PrTitle,
    PullRequest,
    PullRequests,
    ReviewBody,
    ReviewDecision,
    ReviewRequest,
)
from mb_workflow.c_infrastructure.github import GitHub, ReviewId, UserLogin
from mb_workflow.c_infrastructure.shell import (
    Command,
    CommandOutput,
    CommandRunner,
    ExistingDirectory,
)

if TYPE_CHECKING:
    from pathlib import Path

    from mb_workflow.b_core.c_secondary_ports.code_review import CodeReview


class ReviewKind(StrEnum):
    fake = "fake"
    github = "github"


class ReviewLedger(Protocol):
    def submitted(self) -> tuple[SubmittedReview, ...]: ...

    def checked_out(self, into: CheckoutDirectory) -> PrNumber | None: ...


def unreviewed() -> PullRequest:
    return PullRequest(number=PrNumber(7), title=PrTitle("Other work"), branch=BranchName("other"))


def requested() -> PullRequests:
    return PullRequests((PullRequest.fake(), unreviewed()))


def merged(branch: BranchName, on: MergedOn) -> MergedPullRequest:
    return MergedPullRequest(
        pull_request=PullRequest.fake().model_copy(update={"branch": branch}), merged_on=on
    )


def merges() -> tuple[MergedPullRequest, ...]:
    return (
        merged(BranchName("feat/before"), MergedOn(date(2026, 8, 8))),
        merged(BranchName("feat/on-the-day"), MergedOn(date(2026, 8, 9))),
        merged(BranchName("feat/after"), MergedOn(date(2026, 9, 1))),
    )


def pending() -> tuple[PrNumber, ...]:
    return (PrNumber.fake(),)


FLAGS = {
    "--approve": ReviewDecision.approve,
    "--request-changes": ReviewDecision.request_changes,
    "--comment": ReviewDecision.comment,
}
EVENTS = {
    "APPROVE": ReviewDecision.approve,
    "REQUEST_CHANGES": ReviewDecision.request_changes,
    "COMMENT": ReviewDecision.comment,
}


def as_json(prs: tuple[PullRequest, ...]) -> CommandOutput:
    return CommandOutput(
        json.dumps(
            [
                {"number": pr.number.root, "title": pr.title.root, "headRefName": pr.branch.root}
                for pr in prs
            ]
        )
    )


class ScriptedGh(CommandRunner):
    def __init__(self, directory: ExistingDirectory, shared: ScriptedGhState) -> None:
        self._directory = directory
        self._state = shared

    @override
    def cwd(self) -> ExistingDirectory:
        return self._directory

    @override
    def at(self, directory: ExistingDirectory) -> ScriptedGh:
        return ScriptedGh(directory, self._state)

    @override
    def run(self, command: Command) -> CommandOutput:
        return self._state.respond(command, self._directory)

    def submitted(self) -> tuple[SubmittedReview, ...]:
        return tuple(self._state.submitted)

    def checked_out(self, into: CheckoutDirectory) -> PrNumber | None:
        return self._state.checkouts.get(into.root.resolve())


class ScriptedGhState:
    def __init__(self) -> None:
        self.viewer = UserLogin.fake()
        self.pending = {pr: ReviewId(5000 + pr.root) for pr in pending()}
        self.submitted: list[SubmittedReview] = []
        self.checkouts: dict[Path, PrNumber] = {}

    def respond(self, command: Command, directory: ExistingDirectory) -> CommandOutput:
        match command.root:
            case ("gh", "--version"):
                return CommandOutput("gh version 2.0.0\n")
            case ("gh", "pr", "list", "--search", "is:open review-requested:@me", "--json", _):
                return as_json(requested().root)
            case ("gh", "pr", "list", "--state", "merged", "--search", query, "--limit", _, *_):
                since = date.fromisoformat(query.removeprefix("merged:>="))
                return as_json(tuple(m.pull_request for m in merges() if m.merged_on.root >= since))
            case ("gh", "api", "user", "--jq", ".login"):
                return CommandOutput(f"{self.viewer.root}\n")
            case ("gh", "api", "--paginate", "--slurp", path):
                return self.reviews_on(PrNumber(int(path.split("/")[-2])))
            case _:
                return self.respond_to_write(command, directory)

    def respond_to_write(self, command: Command, directory: ExistingDirectory) -> CommandOutput:
        match command.root:
            case ("gh", "pr", "checkout", number, "--force"):
                self.checkouts[directory.root.resolve()] = PrNumber(int(number))
                return CommandOutput("")
            case ("gh", "pr", "review", number, flag, *body):
                self.record_submission(
                    PrNumber(int(number)),
                    ReviewRequest(
                        decision=FLAGS[flag], body=ReviewBody(body[-1] if len(body) > 0 else "")
                    ),
                    Drafted(False),
                )
                return CommandOutput("")
            case ("gh", "api", "--method", "POST", path, "--silent", "-f", event, *body):
                *_, number, _, review, _ = path.split("/")
                pr = PrNumber(int(number))
                if self.pending.pop(pr, None) != ReviewId(int(review)):
                    raise AssertionError(f"No pending review {review} on #{number}")
                text = body[-1].removeprefix("body=") if len(body) > 0 else ""
                self.record_submission(
                    pr,
                    ReviewRequest(
                        decision=EVENTS[event.removeprefix("event=")], body=ReviewBody(text)
                    ),
                    Drafted(True),
                )
                return CommandOutput("")
            case _:
                raise AssertionError(f"gh has no answer for {command.root}")

    # Someone else's pending review sits first, so the adapter must pick out the viewer's own.
    def reviews_on(self, pr: PrNumber) -> CommandOutput:
        others = [{"id": 1, "state": "PENDING", "user": {"login": "someone"}}]
        mine = [
            {"id": review.root, "state": "PENDING", "user": {"login": self.viewer.root}}
            for pending_pr, review in self.pending.items()
            if pending_pr == pr
        ]
        return CommandOutput(json.dumps([others, mine]))

    def record_submission(self, pr: PrNumber, request: ReviewRequest, drafted: Drafted) -> None:
        self.submitted.append(SubmittedReview(pr=pr, request=request, drafted=drafted))


@pytest.fixture(params=list(ReviewKind))
def kind(request: pytest.FixtureRequest) -> ReviewKind:
    return ReviewKind(request.param)


@pytest.fixture
def ledger(kind: ReviewKind) -> FakeCodeReview | ScriptedGh:
    if kind == ReviewKind.github:
        return ScriptedGh(ExistingDirectory.fake(), ScriptedGhState())
    return FakeCodeReview(requested(), merges(), pending())


@pytest.fixture
def review(ledger: FakeCodeReview | ScriptedGh) -> CodeReview:
    if isinstance(ledger, ScriptedGh):
        return GitHub(ledger)
    return ledger


def test_lists_the_pull_requests_awaiting_review(review: CodeReview) -> None:
    assert review.review_requested() == requested()


def test_lists_the_branches_merged_since_a_date_inclusive(review: CodeReview) -> None:
    assert set(review.merged_branches(MergedSince.fake()).root) == {
        BranchName("feat/on-the-day"),
        BranchName("feat/after"),
    }


def test_a_checkout_lands_in_the_directory_it_was_given(
    review: CodeReview, ledger: ReviewLedger, tmp_path: Path
) -> None:
    review.checkout(PrNumber.fake(), CheckoutDirectory(tmp_path))
    assert ledger.checked_out(CheckoutDirectory(tmp_path)) == PrNumber.fake()


def test_submitting_completes_my_pending_review(review: CodeReview, ledger: ReviewLedger) -> None:
    review.submit(PrNumber.fake(), ReviewRequest.fake())
    assert ledger.submitted() == (
        SubmittedReview(pr=PrNumber.fake(), request=ReviewRequest.fake(), drafted=Drafted(True)),
    )


def test_a_pending_review_is_completed_only_once(review: CodeReview, ledger: ReviewLedger) -> None:
    review.submit(PrNumber.fake(), ReviewRequest.fake())
    review.submit(PrNumber.fake(), ReviewRequest.fake())
    assert [submitted.drafted for submitted in ledger.submitted()] == [
        Drafted(True),
        Drafted(False),
    ]


def test_submitting_without_a_pending_review_opens_a_new_one(
    review: CodeReview, ledger: ReviewLedger
) -> None:
    review.submit(PrNumber(7), ReviewRequest.fake())
    assert ledger.submitted() == (
        SubmittedReview(pr=PrNumber(7), request=ReviewRequest.fake(), drafted=Drafted(False)),
    )


def test_an_approval_may_go_without_a_body(review: CodeReview, ledger: ReviewLedger) -> None:
    bare = ReviewRequest(decision=ReviewDecision.approve, body=ReviewBody(""))
    review.submit(PrNumber(7), bare)
    assert ledger.submitted() == (
        SubmittedReview(pr=PrNumber(7), request=bare, drafted=Drafted(False)),
    )


@pytest.mark.parametrize("decision", [ReviewDecision.request_changes, ReviewDecision.comment])
def test_a_decision_that_needs_a_body_is_refused_without_one(
    review: CodeReview, ledger: ReviewLedger, decision: ReviewDecision
) -> None:
    with pytest.raises(CodeReviewError, match="requires comment text"):
        review.submit(PrNumber.fake(), ReviewRequest(decision=decision, body=ReviewBody("")))
    assert ledger.submitted() == ()


def test_requesting_changes_carries_its_body(review: CodeReview, ledger: ReviewLedger) -> None:
    rejection = ReviewRequest(
        decision=ReviewDecision.request_changes, body=ReviewBody("Needs a test.")
    )
    review.submit(PrNumber(7), rejection)
    assert ledger.submitted() == (
        SubmittedReview(pr=PrNumber(7), request=rejection, drafted=Drafted(False)),
    )


def test_checking_out_into_a_missing_directory_is_refused(
    review: CodeReview, tmp_path: Path
) -> None:
    with pytest.raises(CodeReviewError):
        review.checkout(PrNumber.fake(), CheckoutDirectory(tmp_path / "missing"))
