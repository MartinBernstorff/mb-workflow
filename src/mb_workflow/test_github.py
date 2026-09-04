from mb_workflow.git import BranchName
from mb_workflow.github import PrNumber, PrTitle, PullRequest, PullRequests
from mb_workflow.shell import CommandOutput


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
