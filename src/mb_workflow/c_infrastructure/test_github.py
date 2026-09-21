from mb_workflow.b_core.git import BranchName
from mb_workflow.b_core.pull_request import PrNumber, PrTitle
from mb_workflow.c_infrastructure.github import (
    PullRequest,
    PullRequests,
    Review,
    ReviewAuthor,
    ReviewBody,
    ReviewDecision,
    ReviewId,
    ReviewRequest,
    Reviews,
    ReviewState,
    UserLogin,
)
from mb_workflow.c_infrastructure.shell import CommandOutput


def test_parses_gh_pr_list_output() -> None:
    output = CommandOutput(
        '[{"number":1234,"title":"Add review workspaces","headRefName":"feat/review-workspaces"}]'
    )
    assert PullRequests.parse(output) == PullRequests((PullRequest.fake(),))


def test_parses_empty_gh_pr_list_output() -> None:
    assert PullRequests.parse(CommandOutput("[]")) == PullRequests(())


def test_ignores_fields_we_do_not_read() -> None:
    output = CommandOutput(
        '[{"number":1234,"title":"Add review workspaces",'
        '"headRefName":"feat/review-workspaces",'
        '"reviewRequests":[{"login":"MartinBernstorff"}]}]'
    )
    parsed = PullRequests.parse(output).root[0]
    assert parsed.number == PrNumber.fake()
    assert parsed.title == PrTitle.fake()
    assert parsed.head_ref_name == BranchName.fake()


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
    assert ReviewRequest.fake().submission(PrNumber.fake(), ReviewId.fake()).root == (
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
    request = ReviewRequest(decision=ReviewDecision.comment(), body=ReviewBody(""))
    assert request.submission(PrNumber.fake(), ReviewId.fake()).root == (
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
