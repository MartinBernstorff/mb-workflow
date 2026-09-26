import pytest

from mb_workflow.b_core.a_features.open_issue import OpenRequest, issue_state, open_workspace
from mb_workflow.b_core.c_secondary_ports.issue_tracker import FakeIssueTracker, TrackedIssue
from mb_workflow.b_core.c_secondary_ports.status import FakeStatusStore
from mb_workflow.b_core.c_secondary_ports.workspace_manager import FakeWorkspaceManager
from mb_workflow.b_core.d_domain_model.flow import (
    AwaitingHuman,
    FlowError,
    Skill,
    StateName,
    StateNames,
    WorkflowChart,
)
from mb_workflow.b_core.d_domain_model.issue import (
    Assigned,
    Issue,
    IssueIdentifier,
    LabelNames,
    StatusName,
)
from mb_workflow.b_core.d_domain_model.workspace import (
    TerminalText,
    WorkspaceStatuses,
    Worktree,
    WorktreePath,
    Worktrees,
)


def tracking(status: StatusName) -> FakeIssueTracker:
    issue = Issue.fake().model_copy(update={"status": status})
    return FakeIssueTracker(
        LabelNames.fake(), (TrackedIssue.fake().model_copy(update={"issue": issue}),)
    )


def board() -> FakeStatusStore:
    return FakeStatusStore(StateName.fake())


def manager() -> FakeWorkspaceManager:
    columns = WorkspaceStatuses(
        tuple(board().column_for(state) for state in StateNames.of_chart(WorkflowChart).root)
    )
    return FakeWorkspaceManager(Worktrees.fake(), WorktreePath.fake(), columns)


def opened_in(manager: FakeWorkspaceManager) -> Worktree:
    (opened,) = manager.worktrees().without(WorktreePath.fake()).root
    return opened


def test_the_skill_leads_the_prompt() -> None:
    directed = OpenRequest.fake().directed(Skill("/implement"))
    assert directed.prompt == TerminalText(f"/implement {TerminalText.fake().root}")


def test_waiting_for_a_human_leaves_nothing_to_prompt() -> None:
    assert OpenRequest.fake().directed(AwaitingHuman()).prompt is None


def test_an_issue_without_an_action_leaves_the_prompt_alone() -> None:
    assert OpenRequest.fake().directed(None) == OpenRequest.fake()


def test_no_prompt_means_nothing_to_prefix() -> None:
    promptless = OpenRequest.fake().model_copy(update={"prompt": None})
    assert promptless.directed(Skill("/implement")) == promptless


def test_reads_the_status_of_the_tracked_issue_as_a_state() -> None:
    tracker = tracking(StatusName("Speccing"))
    assert issue_state(tracker, IssueIdentifier.fake()) == StateName("Speccing")


def test_a_status_outside_the_chart_is_a_clear_error() -> None:
    with pytest.raises(FlowError, match="Marinating is no state of the chart"):
        _ = issue_state(tracking(StatusName("Marinating")), IssueIdentifier.fake())


def test_an_issue_the_tracker_cannot_read_has_no_state() -> None:
    tracker = tracking(StatusName.fake())
    assert issue_state(tracker, IssueIdentifier("E-404")) is None


def test_no_issue_has_no_state() -> None:
    assert issue_state(tracking(StatusName.fake()), None) is None


def test_opens_a_worktree_linked_to_the_issue() -> None:
    opening = manager()
    open_workspace(opening, tracking(StatusName("Specced")), board(), OpenRequest.fake())
    assert opened_in(opening).issue == IssueIdentifier.fake()


@pytest.mark.parametrize(
    ("status", "skill"),
    [
        (StatusName("Backlog"), Skill("/grill")),
        (StatusName("Grilling"), Skill("/grill")),
        (StatusName("Speccing"), Skill("/to-ticket")),
        (StatusName("Specced"), Skill("/implement")),
    ],
)
def test_types_the_prompt_led_by_the_skill_for_the_issues_state(
    status: StatusName, skill: Skill
) -> None:
    opening = manager()
    open_workspace(opening, tracking(status), board(), OpenRequest.fake())
    assert opening.typed_texts() == (TerminalText(f"{skill.root} {TerminalText.fake().root}"),)


def test_an_issue_waiting_for_a_human_is_opened_without_a_prompt() -> None:
    opening = manager()
    open_workspace(opening, tracking(StatusName("QA")), board(), OpenRequest.fake())
    assert opening.typed_texts() == ()
    assert opened_in(opening).issue == IssueIdentifier.fake()


def test_seeds_the_board_column_from_the_issues_state() -> None:
    opening = manager()
    open_workspace(opening, tracking(StatusName("Backlog")), board(), OpenRequest.fake())
    assert opened_in(opening).status == board().column_for(StateName("Grilling"))


def test_an_issue_the_tracker_cannot_read_is_opened_in_no_column() -> None:
    opening = manager()
    unreadable = OpenRequest.fake().model_copy(update={"issue": IssueIdentifier("E-404")})
    open_workspace(opening, tracking(StatusName.fake()), board(), unreadable)
    assert opened_in(opening).status is None


def test_assigns_the_issue_it_opens() -> None:
    tracker = tracking(StatusName("Specced"))
    open_workspace(manager(), tracker, board(), OpenRequest.fake())
    assert tracker.read_issue(IssueIdentifier.fake()).assigned == Assigned(True)


def test_without_a_prompt_nothing_is_typed() -> None:
    opening = manager()
    promptless = OpenRequest.fake().model_copy(update={"prompt": None})
    open_workspace(opening, tracking(StatusName("Specced")), board(), promptless)
    assert opening.typed_texts() == ()


@pytest.mark.parametrize(
    "status", [StatusName("Merged"), StatusName("Canceled"), StatusName("Duplicate")]
)
def test_an_issue_with_no_work_left_is_neither_opened_nor_assigned(status: StatusName) -> None:
    opening = manager()
    tracker = tracking(status)
    with pytest.raises(FlowError, match="no work left"):
        open_workspace(opening, tracker, board(), OpenRequest.fake())
    assert opening.worktrees() == Worktrees.fake()
    assert tracker.read_issue(IssueIdentifier.fake()).assigned == Assigned(False)
