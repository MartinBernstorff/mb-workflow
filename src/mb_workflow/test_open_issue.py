import pytest

from mb_workflow.linear import Issue, IssueState
from mb_workflow.open_issue import OpenRequest, PromptPrefix, UnprefixedStateError
from mb_workflow.orca import TerminalText
from mb_workflow.shell import CommandOutput


def test_a_backlog_issue_is_grilled() -> None:
    assert PromptPrefix.of(IssueState.backlog) == PromptPrefix("/grill")


def test_a_maturing_issue_becomes_a_ticket() -> None:
    assert PromptPrefix.of(IssueState.maturing) == PromptPrefix("/to-ticket")


def test_a_todo_issue_is_implemented() -> None:
    assert PromptPrefix.of(IssueState.todo) == PromptPrefix("/implement")


def test_a_state_with_no_prefix_is_an_error() -> None:
    with pytest.raises(UnprefixedStateError):
        _ = PromptPrefix.of(IssueState.in_progress)


def test_the_prefix_leads_the_prompt() -> None:
    prefixed = OpenRequest.fake().prefixed(IssueState.todo)
    assert prefixed.prompt == TerminalText(f"/implement {TerminalText.fake().root}")


def test_an_issue_without_a_state_leaves_the_prompt_alone() -> None:
    assert OpenRequest.fake().prefixed(None) == OpenRequest.fake()


def test_no_prompt_means_nothing_to_prefix() -> None:
    promptless = OpenRequest.fake().model_copy(update={"prompt": None})
    assert promptless.prefixed(IssueState.in_progress) == promptless


def test_reads_the_state_off_an_issue() -> None:
    output = CommandOutput('{"identifier": "E-4289", "state": {"name": "Maturing"}}')
    assert Issue.parse(output).state == IssueState.maturing


def test_an_unrecognised_state_is_no_state_at_all() -> None:
    output = CommandOutput('{"identifier": "E-4289", "state": {"name": "Marinating"}}')
    with pytest.raises(ValueError, match="state"):
        _ = Issue.parse(output)
