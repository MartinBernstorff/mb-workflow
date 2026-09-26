from mb_workflow.b_core.d_domain_model.git import BranchName
from mb_workflow.b_core.d_domain_model.pull_request import (
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
    PullRequestPayloads,
    Review,
    ReviewAuthor,
    ReviewId,
    Reviews,
    ReviewState,
    SearchQuery,
    UserLogin,
    pending_submission,
    review_command,
)
from mb_workflow.c_infrastructure.shell import CommandOutput


def test_parses_gh_pr_list_output() -> None:
    output = CommandOutput(
        '[{"number":1234,"title":"Add review workspaces","headRefName":"feat/review-workspaces"}]'
    )
    assert PullRequestPayloads.parse(output) == PullRequests((PullRequest.fake(),))


def test_parses_empty_gh_pr_list_output() -> None:
    assert PullRequestPayloads.parse(CommandOutput("[]")) == PullRequests(())


def test_ignores_fields_we_do_not_read() -> None:
    output = CommandOutput(
        '[{"number":1234,"title":"Add review workspaces",'
        '"headRefName":"feat/review-workspaces",'
        '"reviewRequests":[{"login":"MartinBernstorff"}]}]'
    )
    parsed = PullRequestPayloads.parse(output).root[0]
    assert parsed.number == PrNumber.fake()
    assert parsed.title == PrTitle.fake()
    assert parsed.branch == BranchName.fake()


def test_parses_slurped_review_pages() -> None:
    output = CommandOutput(
        '[[{"id":11,"state":"APPROVED","user":{"login":"someone"}}],'
        '[{"id":5678,"state":"PENDING","user":{"login":"MartinBernstorff"}}]]'
    )
    assert Reviews.parse(output) == Reviews(
        (
            Review(
                id=ReviewId(11),
                state=ReviewState("APPROVED"),
                user=ReviewAuthor(login=UserLogin("someone")),
            ),
            Review.fake(),
        )
    )


def test_finds_my_pending_review() -> None:
    assert Reviews.fake().pending_by(UserLogin.fake()) == ReviewId.fake()


def test_ignores_a_pending_review_by_someone_else() -> None:
    assert Reviews.fake().pending_by(UserLogin("someone")) is None


def test_ignores_my_already_submitted_reviews() -> None:
    submitted = Reviews((Review.fake().model_copy(update={"state": ReviewState("APPROVED")}),))
    assert submitted.pending_by(UserLogin.fake()) is None


def test_takes_the_latest_of_my_pending_reviews() -> None:
    reviews = Reviews((Review.fake().model_copy(update={"id": ReviewId(1)}), Review.fake()))
    assert reviews.pending_by(UserLogin.fake()) == ReviewId.fake()


def test_submits_a_pending_review_with_its_body() -> None:
    assert pending_submission(PrNumber.fake(), ReviewId.fake(), ReviewRequest.fake()).root == (
        "gh",
        "api",
        "--method",
        "POST",
        "repos/{owner}/{repo}/pulls/1234/reviews/5678/events",
        "--silent",
        "-f",
        "event=APPROVE",
        "-f",
        "body=Looks good to me.",
    )


def test_submits_a_pending_review_without_a_body() -> None:
    request = ReviewRequest(decision=ReviewDecision.comment, body=ReviewBody(""))
    assert pending_submission(PrNumber.fake(), ReviewId.fake(), request).root == (
        "gh",
        "api",
        "--method",
        "POST",
        "repos/{owner}/{repo}/pulls/1234/reviews/5678/events",
        "--silent",
        "-f",
        "event=COMMENT",
    )


def test_reads_the_viewer_login() -> None:
    assert UserLogin.parse(CommandOutput("MartinBernstorff\n")) == UserLogin.fake()


def test_approval_carries_its_comment() -> None:
    assert review_command(PrNumber.fake(), ReviewRequest.fake()).root == (
        ("gh", "pr", "review", "1234", "--approve", "--body", "Looks good to me.")
    )


def test_an_empty_comment_is_left_off_the_command() -> None:
    request = ReviewRequest(decision=ReviewDecision.approve, body=ReviewBody(""))
    assert review_command(PrNumber.fake(), request).root == (
        "gh",
        "pr",
        "review",
        "1234",
        "--approve",
    )


def test_the_window_searches_for_prs_merged_since_then() -> None:
    assert SearchQuery.merged_since(MergedSince.fake()).root == "merged:>=2026-08-09"
