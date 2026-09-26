import pytest

from mb_workflow.b_core.a_features.start import StartRequest, start_ticket
from mb_workflow.b_core.c_secondary_ports.claims import (
    ClaimRefusedError,
    FakeClaimRegistry,
    FakePause,
)
from mb_workflow.b_core.c_secondary_ports.status import FakeStatusStore
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
    FakeTicketTracker,
    TicketTrackerError,
    TrackedIssue,
)
from mb_workflow.b_core.c_secondary_ports.workspace_manager import FakeWorkspaceManager
from mb_workflow.b_core.d_domain_model.claim import (
    Claim,
    ClaimHolder,
    ClaimId,
    Claims,
    HostName,
    TakeOver,
)
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
    IssueStatusName,
    LabelNames,
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


def tracking(status: IssueStatusName) -> FakeTicketTracker:
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


def starting(
    manager: FakeWorkspaceManager,
    tracker: FakeTicketTracker,
    request: StartRequest,
    claims: FakeClaimRegistry | None = None,
    workspace: WorkspaceSettings | None = None,
) -> None:
    start_ticket(
        manager=manager,
        tracker=tracker,
        claims=claims or FakeClaimRegistry(),
        pause=FakePause(),
        board=fake_board(),
        workspace=workspace or WorkspaceSettings.fake(),
        request=request,
    )


def started(status: IssueStatusName, request: StartRequest) -> FakeWorkspaceManager:
    manager = fake_manager()
    starting(manager, tracking(status), request)
    return manager


def test_opens_a_worktree_named_and_linked_after_the_ticket() -> None:
    opened = opened_in(started(IssueStatusName("Specced"), StartRequest.fake()))
    assert opened.issue == IssueIdentifier.fake()
    assert opened.path == WorktreePath.fake().sibling(WorktreeName.of_issue(IssueIdentifier.fake()))


def test_types_the_prompt_without_submitting_it_by_default() -> None:
    starting = started(IssueStatusName("Specced"), StartRequest.fake())
    assert starting.typed_texts() == (TerminalText("/implement E-4289"),)
    assert starting.submitted_texts() == ()


def test_submits_the_prompt_when_asked_to() -> None:
    submitting = StartRequest.fake().model_copy(update={"submit": Submit(True)})
    assert started(IssueStatusName("Specced"), submitting).submitted_texts() == (
        TerminalText("/implement E-4289"),
    )


@pytest.mark.parametrize(
    ("status", "prompt"),
    [
        (IssueStatusName("Backlog"), TerminalText("/grill E-4289")),
        (IssueStatusName("Grilling"), TerminalText("/grill E-4289")),
        (IssueStatusName("Speccing"), TerminalText("/to-ticket E-4289")),
        (IssueStatusName("Specced"), TerminalText("/implement E-4289")),
    ],
)
def test_the_prompt_is_the_next_action_for_the_tickets_state(
    status: IssueStatusName, prompt: TerminalText
) -> None:
    assert started(status, StartRequest.fake()).typed_texts() == (prompt,)


def test_a_ticket_waiting_for_a_human_is_opened_without_a_prompt() -> None:
    starting = started(IssueStatusName("QA"), StartRequest.fake())
    assert starting.typed_texts() == ()
    assert opened_in(starting).issue == IssueIdentifier.fake()


def test_seeds_the_board_column_from_the_tickets_state() -> None:
    opened = opened_in(started(IssueStatusName("Backlog"), StartRequest.fake()))
    assert opened.status == fake_board().status_for(StateName("Grilling"))


def test_a_ticket_the_tracker_cannot_read_is_not_opened() -> None:
    manager = fake_manager()
    unreadable = StartRequest.fake().model_copy(update={"ticket": IssueIdentifier("E-404")})
    with pytest.raises(TicketTrackerError):
        starting(manager, tracking(IssueStatusName.fake()), unreadable)
    assert manager.worktrees() == Worktrees.fake()


def test_opens_the_worktree_in_the_configured_project() -> None:
    project = ProjectSelector("github:other/project")
    manager = FakeWorkspaceManager(
        Worktrees.fake(), WorktreePath.fake(), fake_board_statuses(), project=project
    )
    workspace = WorkspaceSettings.fake().model_copy(update={"orca_project": project})
    starting(
        manager, tracking(IssueStatusName("Specced")), StartRequest.fake(), workspace=workspace
    )
    assert opened_in(manager).issue == IssueIdentifier.fake()


def test_assigns_the_ticket_to_the_configured_assignee() -> None:
    tracker = tracking(IssueStatusName("Specced"))
    assignee = Assignee("other@flowbase.io")
    workspace = WorkspaceSettings.fake().model_copy(update={"assignee": assignee})
    starting(fake_manager(), tracker, StartRequest.fake(), workspace=workspace)
    assert tracker.read_issue_detail(IssueIdentifier.fake()).assignee == assignee


@pytest.mark.parametrize(
    "status", [IssueStatusName("Merged"), IssueStatusName("Canceled"), IssueStatusName("Duplicate")]
)
def test_a_ticket_with_no_work_left_is_neither_opened_nor_assigned(status: IssueStatusName) -> None:
    manager = fake_manager()
    tracker = tracking(status)
    claims = FakeClaimRegistry()
    with pytest.raises(FlowError, match="no work left"):
        starting(manager, tracker, StartRequest.fake(), claims)
    assert manager.worktrees() == Worktrees.fake()
    assert tracker.read_issue(IssueIdentifier.fake()).assigned == Assigned(False)
    assert claims.claims(IssueIdentifier.fake()) == Claims(())


def ours() -> ClaimHolder:
    return ClaimHolder(
        host=StartRequest.fake().host, worktree=WorktreeName.of_issue(IssueIdentifier.fake())
    )


def claimed_by_a_rival() -> FakeClaimRegistry:
    rival = ClaimHolder(
        host=HostName("bob-mbp.local"), worktree=WorktreeName.of_issue(IssueIdentifier.fake())
    )
    return FakeClaimRegistry(
        {IssueIdentifier.fake(): Claims((Claim(id=ClaimId("rival"), holder=rival),))}
    )


def holders(claims: FakeClaimRegistry) -> tuple[ClaimHolder, ...]:
    return tuple(claim.holder for claim in claims.claims(IssueIdentifier.fake()).root)


def test_claims_the_ticket_for_this_host_and_worktree() -> None:
    claims = FakeClaimRegistry()
    starting(fake_manager(), tracking(IssueStatusName("Specced")), StartRequest.fake(), claims)
    assert holders(claims) == (ours(),)


def test_the_claim_settles_before_it_is_verified() -> None:
    pause = FakePause()
    start_ticket(
        manager=fake_manager(),
        tracker=tracking(IssueStatusName("Specced")),
        claims=FakeClaimRegistry(),
        pause=pause,
        board=fake_board(),
        workspace=WorkspaceSettings.fake(),
        request=StartRequest.fake(),
    )
    assert pause.waited() == (StartRequest.fake().settle,)


def test_a_ticket_claimed_by_another_holder_is_neither_opened_nor_assigned() -> None:
    manager = fake_manager()
    tracker = tracking(IssueStatusName("Specced"))
    with pytest.raises(ClaimRefusedError, match=r"bob-mbp\.local"):
        starting(manager, tracker, StartRequest.fake(), claimed_by_a_rival())
    assert manager.worktrees() == Worktrees.fake()
    assert tracker.read_issue(IssueIdentifier.fake()).assigned == Assigned(False)


def test_force_takes_the_claim_over() -> None:
    manager = fake_manager()
    claims = claimed_by_a_rival()
    forcing = StartRequest.fake().model_copy(update={"take_over": TakeOver(True)})
    starting(manager, tracking(IssueStatusName("Specced")), forcing, claims)
    assert holders(claims) == (ours(),)
    assert opened_in(manager).issue == IssueIdentifier.fake()


def test_a_ticket_this_worktree_already_claimed_is_not_claimed_twice() -> None:
    claims = FakeClaimRegistry(
        {IssueIdentifier.fake(): Claims((Claim(id=ClaimId("ours"), holder=ours()),))}
    )
    starting(fake_manager(), tracking(IssueStatusName("Specced")), StartRequest.fake(), claims)
    assert holders(claims) == (ours(),)
