import json
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from subprocess import CalledProcessError
from typing import TYPE_CHECKING, Protocol, override

import pytest
from safe_result import Err, Ok

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
from mb_workflow.c_infrastructure.github import (
    GitHub,
    ReviewAuthor,
    ReviewId,
    ReviewState,
    UserLogin,
)
from mb_workflow.c_infrastructure.shell import (
    Command,
    CommandOutput,
    CommandRunner,
    ExistingDirectory,
    Shell,
)
from mb_workflow.d_lib.models import Model, Payload, Value

if TYPE_CHECKING:
    from pathlib import Path

    from mb_workflow.b_core.c_secondary_ports.code_review import CodeForge


class ReviewKind(StrEnum):
    fake = "fake"
    github = "github"
    github_live = "github_live"


class Stage(Model):
    pending: PrNumber
    fresh: PrNumber
    merged: BranchName
    merged_on: MergedOn

    @staticmethod
    def fake() -> Stage:
        return Stage(
            pending=PrNumber.fake(),
            fresh=PrNumber(7),
            merged=BranchName("feat/on-the-day"),
            merged_on=MergedOn(date(2026, 8, 9)),
        )


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
                    pytest.fail(f"No pending review {review} on #{number}")
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
                pytest.fail(f"gh has no answer for {command.root}")

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


class RepositorySlug(Value[str]):
    @staticmethod
    def fake() -> RepositorySlug:
        return RepositorySlug.of_owner(UserLogin.fake())

    @staticmethod
    def of_owner(owner: UserLogin) -> RepositorySlug:
        return RepositorySlug(f"{owner.root}/mb-workflow-integration-test")


class MergedAt(Value[datetime]):
    @staticmethod
    def fake() -> MergedAt:
        return MergedAt(datetime(2026, 8, 9, 12, 0, tzinfo=UTC))


class ListedPullRequest(Payload):
    number: PrNumber
    merged_at: MergedAt | None

    @staticmethod
    def fake() -> ListedPullRequest:
        return ListedPullRequest(number=PrNumber.fake(), merged_at=None)


class ListedPullRequests(Value[tuple[ListedPullRequest, ...]]):
    @staticmethod
    def fake() -> ListedPullRequests:
        return ListedPullRequests((ListedPullRequest.fake(),))

    @staticmethod
    def on_branch(clone: Shell, branch: BranchName) -> ListedPullRequests:
        return ListedPullRequests.model_validate_json(
            clone.run(
                Command(
                    (
                        "gh",
                        "pr",
                        "list",
                        "--head",
                        branch.root,
                        "--state",
                        "all",
                        "--json",
                        "number,mergedAt",
                    )
                )
            ).root
        )

    def merged(self) -> ListedPullRequest | None:
        return next((listed for listed in self.root if listed.merged_at is not None), None)


class LiveReview(Payload):
    id: ReviewId
    state: ReviewState
    body: ReviewBody
    user: ReviewAuthor

    @staticmethod
    def fake() -> LiveReview:
        return LiveReview(
            id=ReviewId.fake(),
            state=ReviewState("COMMENTED"),
            body=ReviewBody.fake(),
            user=ReviewAuthor.fake(),
        )

    def request(self) -> ReviewRequest:
        match self.state.root:
            case "APPROVED":
                decision = ReviewDecision.approve
            case "CHANGES_REQUESTED":
                decision = ReviewDecision.request_changes
            case _:
                decision = ReviewDecision.comment
        return ReviewRequest(decision=decision, body=self.body)


class LiveReviews(Value[tuple[LiveReview, ...]]):
    @staticmethod
    def fake() -> LiveReviews:
        return LiveReviews((LiveReview.fake(),))

    @staticmethod
    def on(clone: Shell, pr: PrNumber, author: UserLogin) -> LiveReviews:
        pages = LiveReviewPages.model_validate_json(
            clone.run(
                Command(
                    (
                        "gh",
                        "api",
                        "--paginate",
                        "--slurp",
                        f"repos/{{owner}}/{{repo}}/pulls/{pr.root}/reviews",
                    )
                )
            ).root
        )
        return LiveReviews(
            tuple(review for page in pages.root for review in page if review.user.login == author)
        )

    def pending(self) -> tuple[ReviewId, ...]:
        return tuple(review.id for review in self.root if review.state == ReviewState.pending())

    def submitted_after(self, seen: tuple[ReviewId, ...]) -> LiveReviews:
        return LiveReviews(
            tuple(
                review
                for review in self.root
                if review.id not in seen and review.state != ReviewState.pending()
            )
        )


class LiveReviewPages(Value[tuple[tuple[LiveReview, ...], ...]]):
    @staticmethod
    def fake() -> LiveReviewPages:
        return LiveReviewPages(((LiveReview.fake(),),))


class LiveGitHub:
    def __init__(self, clone: Shell, stage: Stage, viewer: UserLogin) -> None:
        self._clone = clone
        self._stage = stage
        self._viewer = viewer
        self._seen: tuple[ReviewId, ...] = ()
        self._drafted: ReviewId | None = None

    def reset(self) -> None:
        for pr in (self._stage.pending, self._stage.fresh):
            for review in self.reviews_on(pr).pending():
                _ = self._clone.run(
                    Command(
                        (
                            "gh",
                            "api",
                            "--method",
                            "DELETE",
                            f"repos/{{owner}}/{{repo}}/pulls/{pr.root}/reviews/{review.root}",
                            "--silent",
                        )
                    )
                )
        self._seen = tuple(
            review.id
            for pr in (self._stage.pending, self._stage.fresh)
            for review in self.reviews_on(pr).root
        )
        drafted = self._clone.run(
            Command(
                (
                    "gh",
                    "api",
                    "--method",
                    "POST",
                    f"repos/{{owner}}/{{repo}}/pulls/{self._stage.pending.root}/reviews",
                    "--jq",
                    ".id",
                )
            )
        )
        self._drafted = ReviewId(int(drafted.root))

    def reviews_on(self, pr: PrNumber) -> LiveReviews:
        return LiveReviews.on(self._clone, pr, self._viewer)

    def submitted(self) -> tuple[SubmittedReview, ...]:
        return tuple(
            SubmittedReview(
                pr=pr,
                request=review.request(),
                drafted=Drafted(review.id == self._drafted),
            )
            for pr in (self._stage.pending, self._stage.fresh)
            for review in self.reviews_on(pr).submitted_after(self._seen).root
        )

    def checked_out(self, into: CheckoutDirectory) -> PrNumber | None:
        viewed = Shell(ExistingDirectory(into.root)).run(
            Command(("gh", "pr", "view", "--json", "number", "--jq", ".number"))
        )
        return PrNumber(int(viewed.root))


class LiveRepository(Model):
    clone: ExistingDirectory
    stage: Stage
    viewer: UserLogin

    @staticmethod
    def fake() -> LiveRepository:
        return LiveRepository(
            clone=ExistingDirectory.fake(), stage=Stage.fake(), viewer=UserLogin.fake()
        )

    def shell(self) -> Shell:
        return Shell(self.clone)


def open_pull_request(clone: Shell, branch: BranchName) -> PrNumber:
    listed = ListedPullRequests.on_branch(clone, branch).root
    if len(listed) > 0:
        return listed[0].number
    for step in (
        ("git", "switch", "--quiet", "--create", branch.root, "origin/main"),
        ("git", "commit", "--quiet", "--allow-empty", "--message", f"contract: {branch.root}"),
        ("git", "push", "--quiet", "--set-upstream", "origin", branch.root),
        ("gh", "pr", "create", "--head", branch.root, "--title", branch.root, "--body", ""),
        ("git", "switch", "--quiet", "main"),
    ):
        _ = clone.run(Command(step))
    return ListedPullRequests.on_branch(clone, branch).root[0].number


def merged_pull_request(clone: Shell, branch: BranchName) -> MergedOn:
    merged = ListedPullRequests.on_branch(clone, branch).merged()
    if merged is None:
        pr = open_pull_request(clone, branch)
        _ = clone.run(Command(("gh", "pr", "merge", str(pr.root), "--merge")))
        merged = ListedPullRequests.on_branch(clone, branch).merged()
    if merged is None or merged.merged_at is None:
        pytest.fail(f"GitHub did not merge {branch.root}.")
    return MergedOn(merged.merged_at.root.date())


# Never torn down: reviews accumulate, and the ledger tells this test's apart from earlier ones by id.
@pytest.fixture(scope="session")
def live_repository(tmp_path_factory: pytest.TempPathFactory) -> LiveRepository:
    here = Shell(ExistingDirectory(tmp_path_factory.mktemp("github")))
    viewer = UserLogin.parse(here.run(Command(("gh", "api", "user", "--jq", ".login"))))
    slug = RepositorySlug.of_owner(viewer)
    try:
        _ = here.run(Command(("gh", "repo", "clone", slug.root, "clone", "--", "--quiet")))
    except CalledProcessError:
        pytest.fail(
            f"Create the integration-test repository: gh repo create {slug.root} --private --add-readme"
        )
    clone = Shell(ExistingDirectory(here.cwd().root / "clone"))
    stage = Stage(
        pending=open_pull_request(clone, BranchName("contract/pending")),
        fresh=open_pull_request(clone, BranchName("contract/fresh")),
        merged=BranchName("contract/merged"),
        merged_on=merged_pull_request(clone, BranchName("contract/merged")),
    )
    return LiveRepository(clone=clone.cwd(), stage=stage, viewer=viewer)


@pytest.fixture(
    params=[
        ReviewKind.fake,
        ReviewKind.github,
        pytest.param(ReviewKind.github_live, marks=pytest.mark.github_live),
    ]
)
def kind(request: pytest.FixtureRequest) -> ReviewKind:
    return ReviewKind(request.param)


@pytest.fixture
def stage(kind: ReviewKind, request: pytest.FixtureRequest) -> Stage:
    if kind == ReviewKind.github_live:
        live: LiveRepository = request.getfixturevalue("live_repository")
        return live.stage
    return Stage.fake()


@pytest.fixture
def ledger(
    kind: ReviewKind, request: pytest.FixtureRequest
) -> FakeCodeReview | ScriptedGh | LiveGitHub:
    if kind == ReviewKind.github_live:
        live: LiveRepository = request.getfixturevalue("live_repository")
        ledger = LiveGitHub(live.shell(), live.stage, live.viewer)
        ledger.reset()
        return ledger
    if kind == ReviewKind.github:
        return ScriptedGh(ExistingDirectory.fake(), ScriptedGhState())
    return FakeCodeReview(requested(), merges(), pending())


@pytest.fixture
def review(
    ledger: FakeCodeReview | ScriptedGh | LiveGitHub,
    request: pytest.FixtureRequest,
) -> CodeForge:
    if isinstance(ledger, FakeCodeReview):
        return ledger
    if isinstance(ledger, ScriptedGh):
        return connected(ledger)
    live: LiveRepository = request.getfixturevalue("live_repository")
    return connected(live.shell())


def connected(shell: CommandRunner) -> GitHub:
    match GitHub.connected(shell):
        case Ok(github):
            return github
        case Err(error):
            pytest.fail(str(error))


@pytest.fixture
def checkout_directory(
    kind: ReviewKind, tmp_path: Path, request: pytest.FixtureRequest
) -> CheckoutDirectory:
    if kind != ReviewKind.github_live:
        return CheckoutDirectory(tmp_path)
    live: LiveRepository = request.getfixturevalue("live_repository")
    worktree = tmp_path / "checkout"
    _ = live.shell().run(
        Command(("git", "worktree", "add", "--quiet", "--detach", str(worktree), "origin/main"))
    )
    return CheckoutDirectory(worktree)


def skip_on_own_pull_requests(kind: ReviewKind) -> None:
    if kind == ReviewKind.github_live:
        pytest.skip(
            "GitHub will not request your review on, approve, or request changes to your own PR."
        )


def remark() -> ReviewRequest:
    return ReviewRequest(decision=ReviewDecision.comment, body=ReviewBody.fake())


def test_lists_the_pull_requests_awaiting_review(review: CodeForge, kind: ReviewKind) -> None:
    skip_on_own_pull_requests(kind)
    assert review.review_requested() == Ok(requested())


def test_a_branch_merged_on_the_day_counts_as_merged_since_then(
    review: CodeForge, stage: Stage
) -> None:
    match review.merged_branches(MergedSince(stage.merged_on.root)):
        case Ok(branches):
            assert stage.merged in branches.root
        case Err(error):
            pytest.fail(str(error))


def test_a_branch_merged_the_day_before_does_not(review: CodeForge, stage: Stage) -> None:
    since = MergedSince(stage.merged_on.root + timedelta(days=1))
    match review.merged_branches(since):
        case Ok(branches):
            assert stage.merged not in branches.root
        case Err(error):
            pytest.fail(str(error))


def test_a_checkout_lands_in_the_directory_it_was_given(
    review: CodeForge,
    ledger: ReviewLedger,
    stage: Stage,
    checkout_directory: CheckoutDirectory,
) -> None:
    assert review.checkout(stage.fresh, checkout_directory) == Ok(None)
    assert ledger.checked_out(checkout_directory) == stage.fresh


def test_checking_out_into_a_missing_directory_is_refused(
    review: CodeForge, stage: Stage, tmp_path: Path
) -> None:
    checked_out = review.checkout(stage.fresh, CheckoutDirectory(tmp_path / "missing"))
    assert isinstance(checked_out, Err)
    assert isinstance(checked_out.error, CodeReviewError)


def test_submitting_completes_my_pending_review(
    review: CodeForge, ledger: ReviewLedger, stage: Stage
) -> None:
    assert review.submit(stage.pending, remark()) == Ok(None)
    assert ledger.submitted() == (
        SubmittedReview(pr=stage.pending, request=remark(), drafted=Drafted(True)),
    )


def test_a_pending_review_is_completed_only_once(
    review: CodeForge, ledger: ReviewLedger, stage: Stage
) -> None:
    assert review.submit(stage.pending, remark()) == Ok(None)
    assert review.submit(stage.pending, remark()) == Ok(None)
    assert [submitted.drafted for submitted in ledger.submitted()] == [
        Drafted(True),
        Drafted(False),
    ]


def test_submitting_without_a_pending_review_opens_a_new_one(
    review: CodeForge, ledger: ReviewLedger, stage: Stage
) -> None:
    assert review.submit(stage.fresh, remark()) == Ok(None)
    assert ledger.submitted() == (
        SubmittedReview(pr=stage.fresh, request=remark(), drafted=Drafted(False)),
    )


def test_an_approval_may_go_without_a_body(
    review: CodeForge, ledger: ReviewLedger, stage: Stage, kind: ReviewKind
) -> None:
    skip_on_own_pull_requests(kind)
    bare = ReviewRequest(decision=ReviewDecision.approve, body=ReviewBody(""))
    assert review.submit(stage.fresh, bare) == Ok(None)
    assert ledger.submitted() == (
        SubmittedReview(pr=stage.fresh, request=bare, drafted=Drafted(False)),
    )


def test_requesting_changes_carries_its_body(
    review: CodeForge, ledger: ReviewLedger, stage: Stage, kind: ReviewKind
) -> None:
    skip_on_own_pull_requests(kind)
    rejection = ReviewRequest(
        decision=ReviewDecision.request_changes, body=ReviewBody("Needs a test.")
    )
    assert review.submit(stage.fresh, rejection) == Ok(None)
    assert ledger.submitted() == (
        SubmittedReview(pr=stage.fresh, request=rejection, drafted=Drafted(False)),
    )


@pytest.mark.parametrize("decision", [ReviewDecision.request_changes, ReviewDecision.comment])
def test_a_decision_that_needs_a_body_is_refused_without_one(
    review: CodeForge, ledger: ReviewLedger, stage: Stage, decision: ReviewDecision
) -> None:
    reason = "requires comment text"
    submitted = review.submit(stage.pending, ReviewRequest(decision=decision, body=ReviewBody("")))
    assert isinstance(submitted, Err)
    assert isinstance(submitted.error, CodeReviewError)
    assert reason in str(submitted.error)
    assert ledger.submitted() == ()


class BrokenGh(CommandRunner):
    def __init__(self, output: CommandOutput | None) -> None:
        self._output = output

    @override
    def cwd(self) -> ExistingDirectory:
        return ExistingDirectory.fake()

    @override
    def at(self, directory: ExistingDirectory) -> BrokenGh:
        return self

    @override
    def run(self, command: Command) -> CommandOutput:
        if self._output is None:
            raise CalledProcessError(1, command.root, "", "gh: not authenticated")
        return self._output


def test_connecting_to_a_failing_gh_is_refused() -> None:
    github = GitHub.connected(BrokenGh(None))
    assert isinstance(github, Err)
    assert isinstance(github.error, CodeReviewError)


def test_a_failing_gh_is_returned_as_a_code_review_error(tmp_path: Path) -> None:
    github = GitHub(BrokenGh(None))
    results = (
        github.review_requested(),
        github.merged_branches(MergedSince.fake()),
        github.checkout(PrNumber.fake(), CheckoutDirectory(tmp_path)),
        github.submit(PrNumber.fake(), remark()),
    )
    for result in results:
        assert isinstance(result, Err)
        assert isinstance(result.error, CodeReviewError)


def test_unreadable_gh_output_is_returned_as_a_code_review_error() -> None:
    github = GitHub(BrokenGh(CommandOutput("not json")))
    results = (
        github.review_requested(),
        github.merged_branches(MergedSince.fake()),
        github.submit(PrNumber.fake(), remark()),
    )
    for result in results:
        assert isinstance(result, Err)
        assert isinstance(result.error, CodeReviewError)
