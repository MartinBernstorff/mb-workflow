import pytest

from mb_workflow.b_core.a_features.start import StartRequest, start_ticket
from mb_workflow.b_core.c_secondary_ports.status import FakeStatusStore
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
    FakeTicketTracker,
    TicketTrackerError,
    TrackedIssue,
)
from mb_workflow.b_core.c_secondary_ports.workspace_manager import FakeWorkspaceManager
from mb_workflow.b_core.d_domain_model.config import WorkspaceSettings
from mb_workflow.b_core.d_domain_model.flow import (
    FlowError,
    StateName,
    StateNames,
    WorkflowChart,
)
from mb_workflow.b_core.d_domain_model.issue import (
    Assigned,
    Assignee,
    Issue,
    IssueIdentifier,
    LabelNames,
    StatusName,
)
from mb_workflow.b_core.d_domain_model.workspace import (
    ProjectSelector,
    Submit,
    TerminalText,
    WorkspaceStatuses,
    Worktree,
    WorktreeName,
    WorktreePath,
    Worktrees,
)


def tracking(status: StatusName) -> FakeTicketTracker:
    issue = Issue.fake().model_copy(update={"status": status})
    return FakeTicketTracker(
        LabelNames.fake(), (TrackedIssue.fake().model_copy(update={"issue": issue}),)
    )


def fake_board() -> FakeStatusStore:
    return FakeStatusStore(StateName.fake())


# The fake board names a status for every state, so the manager must hold them all.
def fake_board_statuses() -> WorkspaceStatuses:
    return WorkspaceStatuses(
        tuple(fake_board().status_for(state) for state in StateNames.of_chart(WorkflowChart).root)
    )


def fake_manager() -> FakeWorkspaceManager:
    return FakeWorkspaceManager(Worktrees.fake(), WorktreePath.fake(), fake_board_statuses())


def opened_in(manager: FakeWorkspaceManager) -> Worktree:
    (opened,) = manager.worktrees().without(WorktreePath.fake()).root
    return opened


def started(status: StatusName, request: StartRequest) -> FakeWorkspaceManager:
    manager = fake_manager()
    start_ticket(manager, tracking(status), fake_board(), WorkspaceSettings.fake(), request)
    return manager


def test_opens_a_worktree_named_and_linked_after_the_ticket() -> None:
    opened = opened_in(started(StatusName("Specced"), StartRequest.fake()))
    assert opened.issue == IssueIdentifier.fake()
    assert opened.path == WorktreePath.fake().sibling(WorktreeName("E-4289"))


def test_types_the_prompt_without_submitting_it_by_default() -> None:
    starting = started(StatusName("Specced"), StartRequest.fake())
    assert starting.typed_texts() == (TerminalText("/implement E-4289"),)
    assert starting.submitted_texts() == ()


def test_submits_the_prompt_when_asked_to() -> None:
    submitting = StartRequest.fake().model_copy(update={"submit": Submit(True)})
    assert started(StatusName("Specced"), submitting).submitted_texts() == (
        TerminalText("/implement E-4289"),
    )


@pytest.mark.parametrize(
    ("status", "prompt"),
    [
        (StatusName("Backlog"), TerminalText("/grill E-4289")),
        (StatusName("Grilling"), TerminalText("/grill E-4289")),
        (StatusName("Speccing"), TerminalText("/to-ticket E-4289")),
        (StatusName("Specced"), TerminalText("/implement E-4289")),
    ],
)
def test_the_prompt_is_the_next_action_for_the_tickets_state(
    status: StatusName, prompt: TerminalText
) -> None:
    assert started(status, StartRequest.fake()).typed_texts() == (prompt,)


def test_a_ticket_waiting_for_a_human_is_opened_without_a_prompt() -> None:
    starting = started(StatusName("QA"), StartRequest.fake())
    assert starting.typed_texts() == ()
    assert opened_in(starting).issue == IssueIdentifier.fake()


def test_seeds_the_board_column_from_the_tickets_state() -> None:
    opened = opened_in(started(StatusName("Backlog"), StartRequest.fake()))
    assert opened.status == fake_board().status_for(StateName("Grilling"))


def test_a_ticket_the_tracker_cannot_read_is_not_opened() -> None:
    starting = fake_manager()
    unreadable = StartRequest.fake().model_copy(update={"ticket": IssueIdentifier("E-404")})
    with pytest.raises(TicketTrackerError):
        start_ticket(
            starting,
            tracking(StatusName.fake()),
            fake_board(),
            WorkspaceSettings.fake(),
            unreadable,
        )
    assert starting.worktrees() == Worktrees.fake()


def test_opens_the_worktree_in_the_configured_project() -> None:
    project = ProjectSelector("github:other/project")
    starting = FakeWorkspaceManager(
        Worktrees.fake(), WorktreePath.fake(), fake_board_statuses(), project=project
    )
    workspace = WorkspaceSettings.fake().model_copy(update={"orca_project": project})
    start_ticket(
        starting, tracking(StatusName("Specced")), fake_board(), workspace, StartRequest.fake()
    )
    assert opened_in(starting).issue == IssueIdentifier.fake()


def test_assigns_the_ticket_to_the_configured_assignee() -> None:
    tracker = tracking(StatusName("Specced"))
    assignee = Assignee("other@flowbase.io")
    workspace = WorkspaceSettings.fake().model_copy(update={"assignee": assignee})
    start_ticket(fake_manager(), tracker, fake_board(), workspace, StartRequest.fake())
    assert tracker.read_issue_detail(IssueIdentifier.fake()).assignee == assignee


@pytest.mark.parametrize(
    "status", [StatusName("Merged"), StatusName("Canceled"), StatusName("Duplicate")]
)
def test_a_ticket_with_no_work_left_is_neither_opened_nor_assigned(status: StatusName) -> None:
    starting = fake_manager()
    tracker = tracking(status)
    with pytest.raises(FlowError, match="no work left"):
        start_ticket(starting, tracker, fake_board(), WorkspaceSettings.fake(), StartRequest.fake())
    assert starting.worktrees() == Worktrees.fake()
    assert tracker.read_issue(IssueIdentifier.fake()).assigned == Assigned(False)
