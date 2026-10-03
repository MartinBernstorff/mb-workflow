import pytest

from mb_workflow.b_core.a_features.start import StartRequest, TicketStart
from mb_workflow.b_core.c_secondary_ports.claims import (
    ClaimRefusedError,
    FakeClaimRegistry,
)
from mb_workflow.b_core.c_secondary_ports.status import FakeStatusStore
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
    FakeTicketTracker,
    TicketTrackerError,
    TrackedIssue,
)
from mb_workflow.b_core.c_secondary_ports.workspace_manager import (
    DisplayNameRefusingWorkspaceManager,
    FakeWorkspaceManager,
)
from mb_workflow.b_core.d_domain_model.claim import (
    Claim,
    ClaimHolder,
    ClaimId,
    Claims,
    HostName,
    TakeOver,
)
from mb_workflow.b_core.d_domain_model.config import ClaimSettings, WorkspaceSettings
from mb_workflow.b_core.d_domain_model.flow import (
    FlowError,
    StateName,
    StateNames,
    WorkflowChart,
)
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
from mb_workflow.b_core.d_domain_model.issue import (
    Assigned,
    Assignee,
    Issue,
    IssueIdentifier,
    IssueStatus,
    IssueStatuses,
    IssueStatusName,
    IssueTitle,
    LabelName,
    LabelNames,
    StatusType,
)
from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses
from mb_workflow.b_core.d_domain_model.workspace import (
    Activate,
    DisplayName,
    ProjectSelector,
    Submit,
    TerminalText,
    WorkspaceStatuses,
    Worktree,
    WorktreeName,
    WorktreePath,
    Worktrees,
)


def labelled(state: StateName | None) -> LabelNames:
    flow = () if state is None else (LabelName(state.root),)
    return LabelNames((*LabelNames.fake().root, *flow))


def mapped_statuses() -> IssueStatuses:
    names = dict.fromkeys(TicketStatuses.fake().root.values())
    return IssueStatuses(tuple(IssueStatus(name=name, type=StatusType.started) for name in names))


def tracking(
    state: StateName | None,
    tracker: type[FakeTicketTracker] = FakeTicketTracker,
    status: IssueStatusName = IssueStatusName.fake(),
) -> FakeTicketTracker:
    issue = Issue.fake().model_copy(update={"labels": labelled(state), "status": status})
    return tracker(
        LabelNames((*LabelNames.fake().root, LabelName("claimed"), *FlowLabels.fake().labels.root)),
        (TrackedIssue.fake().model_copy(update={"issue": issue}),),
        statuses=mapped_statuses(),
        groups={FlowLabels.fake().group: FlowLabels.fake().labels},
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
    *,
    workspace: WorkspaceSettings | None = None,
    claim_settings: ClaimSettings | None = None,
) -> None:
    TicketStart.start_ticket(
        manager=manager,
        tracker=tracker,
        claims=claims or FakeClaimRegistry(),
        board=fake_board(),
        workspace=workspace or WorkspaceSettings.fake(),
        claim_settings=claim_settings or ClaimSettings.fake(),
        flow_labels=FlowLabels.fake(),
        statuses=TicketStatuses.fake(),
        request=request,
    )


def started(state: StateName | None, request: StartRequest) -> FakeWorkspaceManager:
    manager = fake_manager()
    starting(manager, tracking(state), request)
    return manager


def test_opens_a_worktree_named_and_linked_after_the_ticket() -> None:
    opened = opened_in(started(StateName("Specced"), StartRequest.fake()))
    assert opened.issue == IssueIdentifier.fake()
    assert opened.path == WorktreePath.fake().sibling(WorktreeName.of_issue(IssueIdentifier.fake()))


def test_names_the_worktree_after_the_ticket_title() -> None:
    opened = opened_in(started(StateName("Specced"), StartRequest.fake()))
    assert opened.display_name == DisplayName.of_issue(IssueTitle.fake())


def test_a_refused_display_name_still_opens_the_worktree() -> None:
    manager = DisplayNameRefusingWorkspaceManager(
        Worktrees.fake(), WorktreePath.fake(), fake_board_statuses()
    )
    starting(manager, tracking(StateName("Specced")), StartRequest.fake())
    assert opened_in(manager).issue == IssueIdentifier.fake()


def test_types_the_prompt_without_submitting_it_by_default() -> None:
    starting = started(StateName("Specced"), StartRequest.fake())
    assert starting.typed_texts() == (TerminalText("/implement E-4289"),)
    assert starting.submitted_texts() == ()


def test_activates_the_worktree_when_asked_to() -> None:
    manager = started(StateName("Specced"), StartRequest.fake())
    assert manager.activated() == (opened_in(manager).path,)


def test_leaves_the_worktree_in_the_background_when_not_asked_to_activate_it() -> None:
    background = StartRequest.fake().model_copy(update={"activate": Activate(False)})
    assert started(StateName("Specced"), background).activated() == ()


def test_submits_the_prompt_when_asked_to() -> None:
    submitting = StartRequest.fake().model_copy(update={"submit": Submit(True)})
    assert started(StateName("Specced"), submitting).submitted_texts() == (
        TerminalText("/implement E-4289"),
    )


@pytest.mark.parametrize(
    ("state", "prompt"),
    [
        (StateName("Grilling"), TerminalText("/grill E-4289")),
        (StateName("Speccing"), TerminalText("/to-ticket E-4289")),
        (StateName("Specced"), TerminalText("/implement E-4289")),
    ],
)
def test_the_prompt_is_the_next_action_for_the_state_of_the_flow_label(
    state: StateName, prompt: TerminalText
) -> None:
    assert started(state, StartRequest.fake()).typed_texts() == (prompt,)


def test_the_ticket_status_does_not_decide_the_state() -> None:
    manager = fake_manager()
    tracker = tracking(StateName("Specced"), status=IssueStatusName("Done"))
    starting(manager, tracker, StartRequest.fake())
    assert manager.typed_texts() == (TerminalText("/implement E-4289"),)


def test_a_ticket_waiting_for_a_human_is_opened_without_a_prompt() -> None:
    starting = started(StateName("QA"), StartRequest.fake())
    assert starting.typed_texts() == ()
    assert opened_in(starting).issue == IssueIdentifier.fake()


def test_seeds_the_board_column_from_the_flow_label() -> None:
    opened = opened_in(started(StateName("Speccing"), StartRequest.fake()))
    assert opened.status == fake_board().status_for(StateName("Speccing"))


def test_a_ticket_without_a_flow_label_is_neither_claimed_assigned_nor_opened() -> None:
    manager = fake_manager()
    tracker = tracking(None)
    claims = FakeClaimRegistry()
    startable = r"--state.*Grilling, Speccing, Specced"
    with pytest.raises(FlowError, match=startable):
        starting(manager, tracker, StartRequest.fake(), claims)
    assert manager.worktrees() == Worktrees.fake()
    assert tracker.read_issue(IssueIdentifier.fake()).assigned == Assigned(False)
    assert claims.claims(IssueIdentifier.fake()) == Claims(())


def starting_in(state: StateName) -> StartRequest:
    return StartRequest.fake().model_copy(update={"state": state})


def test_a_ticket_without_a_flow_label_started_in_a_state_gets_its_label_and_status() -> None:
    manager = fake_manager()
    tracker = tracking(None)
    specced = StateName("Specced")
    starting(manager, tracker, starting_in(specced))
    issue = tracker.read_issue(IssueIdentifier.fake())
    assert issue.labels.has(LabelName(specced.root)).root
    assert issue.status == TicketStatuses.fake().of(specced)
    assert manager.typed_texts() == (TerminalText("/implement E-4289"),)


def test_a_ticket_with_a_flow_label_started_in_a_state_is_not_claimed() -> None:
    manager = fake_manager()
    tracker = tracking(StateName("Grilling"))
    claims = FakeClaimRegistry()
    with pytest.raises(FlowError, match="mw flow"):
        starting(manager, tracker, starting_in(StateName("Specced")), claims)
    assert tracker.read_issue(IssueIdentifier.fake()).labels == labelled(StateName("Grilling"))
    assert claims.claims(IssueIdentifier.fake()) == Claims(())
    assert manager.worktrees() == Worktrees.fake()


def test_a_ticket_started_in_a_state_with_no_work_is_not_claimed() -> None:
    tracker = tracking(None)
    claims = FakeClaimRegistry()
    merged = StateName("Merged")
    with pytest.raises(FlowError, match=merged.root):
        starting(fake_manager(), tracker, starting_in(merged), claims)
    assert tracker.read_issue(IssueIdentifier.fake()).labels == labelled(None)
    assert claims.claims(IssueIdentifier.fake()) == Claims(())


def test_a_ticket_the_tracker_cannot_read_is_not_opened() -> None:
    manager = fake_manager()
    unreadable = StartRequest.fake().model_copy(update={"ticket": IssueIdentifier("E-404")})
    with pytest.raises(TicketTrackerError):
        starting(manager, tracking(StateName.fake()), unreadable)
    assert manager.worktrees() == Worktrees.fake()


def test_opens_the_worktree_in_the_configured_project() -> None:
    project = ProjectSelector("github:other/project")
    manager = FakeWorkspaceManager(
        Worktrees.fake(), WorktreePath.fake(), fake_board_statuses(), project=project
    )
    workspace = WorkspaceSettings.fake().model_copy(update={"orca_project": project})
    starting(manager, tracking(StateName("Specced")), StartRequest.fake(), workspace=workspace)
    assert opened_in(manager).issue == IssueIdentifier.fake()


def test_assigns_the_ticket_to_the_configured_assignee() -> None:
    tracker = tracking(StateName("Specced"))
    assignee = Assignee("other@flowbase.io")
    workspace = WorkspaceSettings.fake().model_copy(update={"assignee": assignee})
    starting(fake_manager(), tracker, StartRequest.fake(), workspace=workspace)
    assert tracker.read_issue_detail(IssueIdentifier.fake()).assignee == assignee


def test_a_merged_ticket_is_neither_opened_nor_assigned() -> None:
    manager = fake_manager()
    tracker = tracking(StateName("Merged"))
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
    starting(fake_manager(), tracking(StateName("Specced")), StartRequest.fake(), claims)
    assert holders(claims) == (ours(),)


def test_a_ticket_claimed_by_another_holder_is_neither_opened_nor_assigned() -> None:
    manager = fake_manager()
    tracker = tracking(StateName("Specced"))
    with pytest.raises(ClaimRefusedError, match=r"bob-mbp\.local"):
        starting(manager, tracker, StartRequest.fake(), claimed_by_a_rival())
    assert manager.worktrees() == Worktrees.fake()
    assert tracker.read_issue(IssueIdentifier.fake()).assigned == Assigned(False)


def test_force_takes_the_claim_over() -> None:
    manager = fake_manager()
    claims = claimed_by_a_rival()
    forcing = StartRequest.fake().model_copy(update={"take_over": TakeOver(True)})
    starting(manager, tracking(StateName("Specced")), forcing, claims)
    assert holders(claims) == (ours(),)
    assert opened_in(manager).issue == IssueIdentifier.fake()


def test_a_ticket_this_worktree_already_claimed_is_not_claimed_twice() -> None:
    claims = FakeClaimRegistry(
        {IssueIdentifier.fake(): Claims((Claim(id=ClaimId("ours"), holder=ours()),))}
    )
    starting(fake_manager(), tracking(StateName("Specced")), StartRequest.fake(), claims)
    assert holders(claims) == (ours(),)


def labels_after_starting(claim_settings: ClaimSettings, claims: FakeClaimRegistry) -> LabelNames:
    tracker = tracking(StateName("Specced"))
    starting(fake_manager(), tracker, StartRequest.fake(), claims, claim_settings=claim_settings)
    return tracker.read_issue(IssueIdentifier.fake()).labels


def test_the_claimed_ticket_carries_the_claim_label() -> None:
    labelling = ClaimSettings(label=LabelName("claimed"))
    assert labels_after_starting(labelling, FakeClaimRegistry()).has(LabelName("claimed")).root


def test_a_ticket_claimed_by_another_holder_is_not_labelled() -> None:
    tracker = tracking(StateName("Specced"))
    labelling = ClaimSettings(label=LabelName("claimed"))
    with pytest.raises(ClaimRefusedError):
        starting(
            fake_manager(),
            tracker,
            StartRequest.fake(),
            claimed_by_a_rival(),
            claim_settings=labelling,
        )
    assert tracker.read_issue(IssueIdentifier.fake()).labels == labelled(StateName("Specced"))


def test_a_claim_label_the_tracker_lacks_fails_the_start_without_leaving_a_claim() -> None:
    manager = fake_manager()
    claims = FakeClaimRegistry()
    missing = ClaimSettings(label=LabelName("absent"))
    with pytest.raises(ClaimRefusedError, match="absent"):
        starting(
            manager,
            tracking(StateName("Specced")),
            StartRequest.fake(),
            claims,
            claim_settings=missing,
        )
    assert claims.claims(IssueIdentifier.fake()) == Claims(())
    assert manager.worktrees() == Worktrees.fake()


def test_a_forced_start_with_a_missing_claim_label_keeps_the_rivals_claim() -> None:
    claims = claimed_by_a_rival()
    forcing = StartRequest.fake().model_copy(update={"take_over": TakeOver(True)})
    missing = ClaimSettings(label=LabelName("absent"))
    with pytest.raises(ClaimRefusedError, match="absent"):
        starting(
            fake_manager(),
            tracking(StateName("Specced")),
            forcing,
            claims,
            claim_settings=missing,
        )
    assert holders(claims) == holders(claimed_by_a_rival())
