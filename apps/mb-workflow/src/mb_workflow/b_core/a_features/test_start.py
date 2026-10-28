import re
from typing import TYPE_CHECKING

import pytest
from safe_result import Err, Ok, Result

from mb_workflow.b_core.a_features.start import StartRequest, TicketStart, WorktreeExistsError
from mb_workflow.b_core.c_secondary_ports.claims import (
    ClaimRefusedError,
    FakeClaimRegistry,
)
from mb_workflow.b_core.c_secondary_ports.status import FakeStatusStore, UnreachableStatusStore
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
    FakeTicketTracker,
    TicketTrackerError,
    TrackedIssue,
)
from mb_workflow.b_core.c_secondary_ports.workspace_manager import (
    DisplayNameRefusingWorkspaceManager,
    FakeWorkspaceManager,
    PriorityRefusingWorkspaceManager,
    WorkspaceManagerError,
)
from mb_workflow.b_core.d_domain_model.claim import (
    Claim,
    ClaimHolder,
    ClaimId,
    Claims,
    HostName,
    TakeOver,
)
from mb_workflow.b_core.d_domain_model.config import FlowSettings, WorkspaceSettings
from mb_workflow.b_core.d_domain_model.flow import (
    FlowError,
    StateName,
    StateNames,
    UnknownStateError,
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
    Priority,
    StatusType,
)
from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses
from mb_workflow.b_core.d_domain_model.workspace import (
    Activate,
    DisplayName,
    ProjectSelector,
    Submit,
    TerminalText,
    WorkspacePriority,
    WorkspaceStatuses,
    Worktree,
    WorktreeName,
    WorktreePath,
    Worktrees,
)

if TYPE_CHECKING:
    from mb_workflow.b_core.b_domain_services.flow_label_check import MissingFlowLabelsError
    from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore


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
    assignee: Assignee | None = None,
    priority: Priority = Priority.medium,
) -> FakeTicketTracker:
    issue = Issue.fake().model_copy(
        update={
            "labels": labelled(state),
            "status": status,
            "assigned": Assigned(assignee is not None),
        }
    )
    return tracker(
        LabelNames((*LabelNames.fake().root, *FlowLabels.fake().labels.root)),
        (
            TrackedIssue.fake().model_copy(
                update={"issue": issue, "assignee": assignee, "priority": priority}
            ),
        ),
        statuses=mapped_statuses(),
        groups={FlowLabels.fake().group: FlowLabels.fake().labels},
    )


def fake_board() -> FakeStatusStore:
    return FakeStatusStore(StateName.fake())


# The fake board names a status for every state, so the manager must hold them all.
def fake_board_statuses() -> WorkspaceStatuses:
    return WorkspaceStatuses(
        tuple(
            fake_board().status_for(state).unwrap()
            for state in StateNames.of_chart(WorkflowChart).root
        )
    )


# The worktree the start runs from, linked to no ticket.
def unlinked_worktrees() -> Worktrees:
    return Worktrees((Worktree.fake().model_copy(update={"issue": None}),))


def fake_manager() -> FakeWorkspaceManager:
    return FakeWorkspaceManager(unlinked_worktrees(), WorktreePath.fake(), fake_board_statuses())


def opened_in(manager: FakeWorkspaceManager) -> Worktree:
    (opened,) = manager.worktrees().unwrap().without(WorktreePath.fake()).root
    return opened


def starting(
    manager: FakeWorkspaceManager,
    tracker: FakeTicketTracker,
    request: StartRequest,
    claims: FakeClaimRegistry | None = None,
    *,
    workspace: WorkspaceSettings | None = None,
    board: WorkspaceStatusStore | None = None,
) -> Result[
    None,
    FlowError
    | TicketTrackerError
    | ClaimRefusedError
    | MissingFlowLabelsError
    | WorkspaceManagerError,
]:
    return TicketStart.start_ticket(
        manager=manager,
        tracker=tracker,
        claims=claims or FakeClaimRegistry(),
        board=board or fake_board(),
        workspace=workspace or WorkspaceSettings.fake(),
        flow_labels=FlowLabels.fake(),
        statuses=TicketStatuses.fake(),
        flow=FlowSettings.fake(),
        request=request,
    )


def started(state: StateName | None, request: StartRequest) -> FakeWorkspaceManager:
    manager = fake_manager()
    assert starting(manager, tracking(state), request) == Ok(None)
    return manager


def test_opens_a_worktree_named_and_linked_after_the_ticket() -> None:
    opened = opened_in(started(StateName("todo"), StartRequest.fake()))
    assert opened.issue == IssueIdentifier.fake()
    assert opened.path == WorktreePath.fake().sibling(WorktreeName.of_issue(IssueIdentifier.fake()))


def test_names_the_worktree_after_the_ticket_title() -> None:
    opened = opened_in(started(StateName("todo"), StartRequest.fake()))
    assert opened.display_name == DisplayName.of_issue(IssueTitle.fake())


def test_a_refused_display_name_still_opens_the_worktree() -> None:
    manager = DisplayNameRefusingWorkspaceManager(
        unlinked_worktrees(), WorktreePath.fake(), fake_board_statuses()
    )
    assert starting(manager, tracking(StateName("todo")), StartRequest.fake()) == Ok(None)
    assert opened_in(manager).issue == IssueIdentifier.fake()


def test_gives_the_worktree_the_ticket_priority() -> None:
    manager = fake_manager()
    assert starting(
        manager, tracking(StateName("todo"), priority=Priority.urgent), StartRequest.fake()
    ) == Ok(None)
    assert opened_in(manager).priority == WorkspacePriority.urgent


def test_a_refused_priority_still_opens_the_worktree() -> None:
    manager = PriorityRefusingWorkspaceManager(
        unlinked_worktrees(), WorktreePath.fake(), fake_board_statuses()
    )
    assert starting(manager, tracking(StateName("todo")), StartRequest.fake()) == Ok(None)
    assert opened_in(manager).issue == IssueIdentifier.fake()


def test_types_the_prompt_without_submitting_it_by_default() -> None:
    starting = started(StateName("todo"), StartRequest.fake())
    assert starting.typed_texts() == (TerminalText("/work E-4289"),)
    assert starting.submitted_texts() == ()


def test_activates_the_worktree_when_asked_to() -> None:
    manager = started(StateName("todo"), StartRequest.fake())
    assert manager.activated() == (opened_in(manager).path,)


def test_leaves_the_worktree_in_the_background_when_not_asked_to_activate_it() -> None:
    background = StartRequest.fake().model_copy(update={"activate": Activate(False)})
    assert started(StateName("todo"), background).activated() == ()


def test_submits_the_prompt_when_asked_to() -> None:
    submitting = StartRequest.fake().model_copy(update={"submit": Submit(True)})
    assert started(StateName("todo"), submitting).submitted_texts() == (
        TerminalText("/work E-4289"),
    )


@pytest.mark.parametrize("state", [StateName("grill"), StateName("to-ticket"), StateName("todo")])
def test_every_state_an_agent_works_types_the_given_prompt_followed_by_the_ticket(
    state: StateName,
) -> None:
    request = StartRequest.fake().model_copy(update={"prompt": TerminalText("/flow")})
    prompt = TerminalText("/flow E-4289")
    assert started(state, request).typed_texts() == (prompt,)


def test_the_ticket_status_does_not_decide_the_state() -> None:
    manager = fake_manager()
    tracker = tracking(StateName("todo"), status=IssueStatusName("Done"))
    assert starting(manager, tracker, StartRequest.fake()) == Ok(None)
    assert manager.typed_texts() == (TerminalText("/work E-4289"),)


def test_a_ticket_waiting_for_a_human_is_opened_without_a_prompt() -> None:
    starting = started(StateName("qa"), StartRequest.fake())
    assert starting.typed_texts() == ()
    assert opened_in(starting).issue == IssueIdentifier.fake()


def test_seeds_the_board_column_from_the_flow_label() -> None:
    opened = opened_in(started(StateName("to-ticket"), StartRequest.fake()))
    assert opened.status == fake_board().status_for(StateName("to-ticket")).unwrap()


def test_a_todo_ticket_opens_in_implementing() -> None:
    manager = fake_manager()
    todo = StateName("todo")
    tracker = tracking(todo)
    implementing = StateName("implementing")
    assert starting(manager, tracker, StartRequest.fake()) == Ok(None)
    issue = tracker.read_issue(IssueIdentifier.fake()).unwrap()
    assert issue.labels.has(LabelName(implementing.root)).root
    assert not issue.labels.has(LabelName(todo.root)).root
    assert issue.status == TicketStatuses.fake().of(implementing)
    assert opened_in(manager).status == fake_board().status_for(implementing).unwrap()


def test_a_grill_ticket_opens_in_grill() -> None:
    manager = fake_manager()
    status = IssueStatusName("Backlog")
    grill = StateName("grill")
    tracker = tracking(grill, status=status)
    assert starting(manager, tracker, StartRequest.fake()) == Ok(None)
    issue = tracker.read_issue(IssueIdentifier.fake()).unwrap()
    assert issue.labels.has(LabelName(grill.root)).root
    assert issue.status == status
    assert opened_in(manager).status == fake_board().status_for(grill).unwrap()


def test_a_ticket_without_a_flow_label_starts_in_the_unlabelled_state() -> None:
    manager = fake_manager()
    tracker = tracking(None)
    unlabelled = FlowSettings.fake().unlabelled_state
    assert starting(manager, tracker, StartRequest.fake()) == Ok(None)
    issue = tracker.read_issue(IssueIdentifier.fake()).unwrap()
    assert issue.labels.has(LabelName(unlabelled.root)).root
    assert opened_in(manager).status == fake_board().status_for(unlabelled).unwrap()


def test_a_board_that_cannot_place_the_ticket_refuses_before_claiming() -> None:
    manager = fake_manager()
    tracker = tracking(StateName("todo"))
    claims = FakeClaimRegistry()
    refused = starting(
        manager, tracker, StartRequest.fake(), claims, board=UnreachableStatusStore()
    )
    assert refused == Err(WorkspaceManagerError("The workspace board is unreachable."))
    assert manager.worktrees().unwrap() == unlinked_worktrees()
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().assigned == Assigned(False)
    assert claims.claims(IssueIdentifier.fake()).unwrap() == Claims(())


def starting_in(state: StateName) -> StartRequest:
    return StartRequest.fake().model_copy(update={"state": state})


def test_a_ticket_without_a_flow_label_started_in_a_state_gets_its_label_and_status() -> None:
    manager = fake_manager()
    tracker = tracking(None)
    to_ticket = StateName("to-ticket")
    assert starting(manager, tracker, starting_in(to_ticket)) == Ok(None)
    issue = tracker.read_issue(IssueIdentifier.fake()).unwrap()
    assert issue.labels.has(LabelName(to_ticket.root)).root
    assert issue.status == TicketStatuses.fake().of(to_ticket)
    assert manager.typed_texts() == (TerminalText("/work E-4289"),)


def test_a_state_typed_in_uppercase_puts_the_ticket_in_the_chart_state() -> None:
    tracker = tracking(None)
    to_ticket = StateName("to-ticket")
    assert starting(fake_manager(), tracker, starting_in(StateName("TO-TICKET"))) == Ok(None)
    issue = tracker.read_issue(IssueIdentifier.fake()).unwrap()
    assert issue.labels.has(LabelName(to_ticket.root)).root
    assert issue.status == TicketStatuses.fake().of(to_ticket)


def test_a_ticket_without_a_flow_label_started_in_todo_opens_in_implementing() -> None:
    manager = fake_manager()
    tracker = tracking(None)
    implementing = StateName("implementing")
    assert starting(manager, tracker, starting_in(StateName("todo"))) == Ok(None)
    issue = tracker.read_issue(IssueIdentifier.fake()).unwrap()
    assert issue.labels.has(LabelName(implementing.root)).root
    assert issue.status == TicketStatuses.fake().of(implementing)
    assert opened_in(manager).status == fake_board().status_for(implementing).unwrap()


def test_a_ticket_with_a_flow_label_started_in_a_state_is_not_claimed() -> None:
    manager = fake_manager()
    tracker = tracking(StateName("grill"))
    claims = FakeClaimRegistry()
    refused = starting(manager, tracker, starting_in(StateName("todo")), claims)
    assert isinstance(refused, Err)
    assert isinstance(refused.error, FlowError)
    assert re.search("mw flow", str(refused.error))
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().labels == labelled(
        StateName("grill")
    )
    assert claims.claims(IssueIdentifier.fake()).unwrap() == Claims(())
    assert manager.worktrees().unwrap() == unlinked_worktrees()


def test_a_ticket_started_in_a_state_with_no_work_is_not_claimed() -> None:
    tracker = tracking(None)
    claims = FakeClaimRegistry()
    refusal = r"No flow state is named merged\. Use one of triage, .*, merging\.$"
    refused = starting(fake_manager(), tracker, starting_in(StateName("merged")), claims)
    assert isinstance(refused, Err)
    assert isinstance(refused.error, UnknownStateError)
    assert re.search(refusal, str(refused.error))
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().labels == labelled(None)
    assert claims.claims(IssueIdentifier.fake()).unwrap() == Claims(())


def test_a_ticket_the_tracker_cannot_read_is_not_opened() -> None:
    manager = fake_manager()
    unreadable = StartRequest.fake().model_copy(update={"ticket": IssueIdentifier("E-404")})
    refused = starting(manager, tracking(StateName.fake()), unreadable)
    assert isinstance(refused, Err)
    assert isinstance(refused.error, TicketTrackerError)
    assert manager.worktrees().unwrap() == unlinked_worktrees()


def test_opens_the_worktree_in_the_configured_project() -> None:
    project = ProjectSelector("github:other/project")
    manager = FakeWorkspaceManager(
        unlinked_worktrees(), WorktreePath.fake(), fake_board_statuses(), project=project
    )
    workspace = WorkspaceSettings.fake().model_copy(update={"orca_project": project})
    assert starting(
        manager, tracking(StateName("todo")), StartRequest.fake(), workspace=workspace
    ) == Ok(None)
    assert opened_in(manager).issue == IssueIdentifier.fake()


def test_assigns_the_ticket_to_the_configured_assignee() -> None:
    tracker = tracking(StateName("todo"))
    assignee = Assignee("other@flowbase.io")
    workspace = WorkspaceSettings.fake().model_copy(update={"assignee": assignee})
    assert starting(fake_manager(), tracker, StartRequest.fake(), workspace=workspace) == Ok(None)
    assert tracker.read_issue_detail(IssueIdentifier.fake()).unwrap().assignee == assignee


def test_a_merged_ticket_is_neither_opened_nor_assigned() -> None:
    manager = fake_manager()
    tracker = tracking(StateName("merged"))
    claims = FakeClaimRegistry()
    refused = starting(manager, tracker, StartRequest.fake(), claims)
    assert isinstance(refused, Err)
    assert isinstance(refused.error, FlowError)
    assert re.search("no work left", str(refused.error))
    assert manager.worktrees().unwrap() == unlinked_worktrees()
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().assigned == Assigned(False)
    assert claims.claims(IssueIdentifier.fake()).unwrap() == Claims(())


def ours() -> ClaimHolder:
    return ClaimHolder(
        host=StartRequest.fake().host, worktree=WorktreeName.of_issue(IssueIdentifier.fake())
    )


def rival_host() -> HostName:
    return HostName("bob-mbp.local")


def claimed_by_a_rival() -> FakeClaimRegistry:
    rival = ClaimHolder(host=rival_host(), worktree=WorktreeName.of_issue(IssueIdentifier.fake()))
    return FakeClaimRegistry(
        {IssueIdentifier.fake(): Claims((Claim(id=ClaimId("rival"), holder=rival),))}
    )


def holders(claims: FakeClaimRegistry) -> tuple[ClaimHolder, ...]:
    return tuple(claim.holder for claim in claims.claims(IssueIdentifier.fake()).unwrap().root)


def test_claims_the_ticket_for_this_host_and_worktree() -> None:
    claims = FakeClaimRegistry()
    assert starting(fake_manager(), tracking(StateName("todo")), StartRequest.fake(), claims) == Ok(
        None
    )
    assert holders(claims) == (ours(),)


def test_a_ticket_claimed_by_another_holder_is_neither_opened_nor_assigned() -> None:
    manager = fake_manager()
    tracker = tracking(StateName("todo"))
    refused = starting(manager, tracker, StartRequest.fake(), claimed_by_a_rival())
    assert isinstance(refused.error, ClaimRefusedError)
    assert re.search(re.escape(rival_host().root), str(refused.error))
    assert manager.worktrees().unwrap() == unlinked_worktrees()
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().assigned == Assigned(False)


def test_force_takes_the_claim_over() -> None:
    manager = fake_manager()
    claims = claimed_by_a_rival()
    forcing = StartRequest.fake().model_copy(update={"take_over": TakeOver(True)})
    assert starting(manager, tracking(StateName("todo")), forcing, claims) == Ok(None)
    assert holders(claims) == (ours(),)
    assert opened_in(manager).issue == IssueIdentifier.fake()


def test_a_ticket_this_worktree_already_claimed_is_not_claimed_twice() -> None:
    claims = FakeClaimRegistry(
        {IssueIdentifier.fake(): Claims((Claim(id=ClaimId("ours"), holder=ours()),))}
    )
    assert starting(fake_manager(), tracking(StateName("todo")), StartRequest.fake(), claims) == Ok(
        None
    )
    assert holders(claims) == (ours(),)


def test_a_ticket_that_already_has_a_worktree_gets_no_second_one() -> None:
    linked = Worktree.fake().model_copy(
        update={"path": WorktreePath.fake().sibling(WorktreeName("elsewhere"))}
    )
    worktrees = Worktrees((*unlinked_worktrees().root, linked))
    manager = FakeWorkspaceManager(worktrees, WorktreePath.fake(), fake_board_statuses())
    tracker = tracking(StateName("todo"))
    claims = FakeClaimRegistry()
    refused = starting(manager, tracker, StartRequest.fake(), claims)
    assert isinstance(refused.error, WorktreeExistsError)
    assert manager.worktrees().unwrap() == worktrees
    assert claims.claims(IssueIdentifier.fake()).unwrap() == Claims(())
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().assigned == Assigned(False)


# Selects no project the workspace settings name, so creating the worktree fails.
def refusing_manager() -> FakeWorkspaceManager:
    return FakeWorkspaceManager(
        unlinked_worktrees(),
        WorktreePath.fake(),
        fake_board_statuses(),
        project=ProjectSelector("github:other/project"),
    )


def test_a_failed_worktree_creation_leaves_no_claim() -> None:
    todo = StateName("todo")
    tracker = tracking(todo)
    claims = FakeClaimRegistry()
    failed = starting(refusing_manager(), tracker, StartRequest.fake(), claims)
    assert isinstance(failed.error, WorkspaceManagerError)
    assert claims.claims(IssueIdentifier.fake()).unwrap() == Claims(())


def test_a_failed_worktree_creation_restores_the_previous_assignee() -> None:
    previous = Assignee("previous@flowbase.io")
    tracker = tracking(StateName("todo"), assignee=previous)
    failed = starting(refusing_manager(), tracker, StartRequest.fake())
    assert isinstance(failed.error, WorkspaceManagerError)
    assert tracker.read_issue_detail(IssueIdentifier.fake()).unwrap().assignee == previous


def test_a_failed_worktree_creation_leaves_an_unassigned_ticket_unassigned() -> None:
    tracker = tracking(StateName("todo"))
    failed = starting(refusing_manager(), tracker, StartRequest.fake())
    assert isinstance(failed.error, WorkspaceManagerError)
    assert tracker.read_issue(IssueIdentifier.fake()).unwrap().assigned == Assigned(False)


def test_a_failed_worktree_creation_moves_a_todo_ticket_back_to_todo() -> None:
    todo = StateName("todo")
    before = IssueStatusName("Maturing")
    tracker = tracking(todo, status=before)
    failed = starting(refusing_manager(), tracker, StartRequest.fake())
    assert isinstance(failed.error, WorkspaceManagerError)
    issue = tracker.read_issue(IssueIdentifier.fake()).unwrap()
    assert issue.labels == labelled(todo)
    assert issue.status == before


def test_a_failed_worktree_creation_takes_an_unlabelled_ticket_back_out_of_the_flow() -> None:
    before = IssueStatusName("Maturing")
    tracker = tracking(None, status=before)
    failed = starting(refusing_manager(), tracker, starting_in(StateName("todo")))
    assert isinstance(failed.error, WorkspaceManagerError)
    issue = tracker.read_issue(IssueIdentifier.fake()).unwrap()
    assert issue.labels == labelled(None)
    assert issue.status == before


def test_a_failed_forced_start_does_not_restore_the_rivals_claim() -> None:
    claims = claimed_by_a_rival()
    forcing = StartRequest.fake().model_copy(update={"take_over": TakeOver(True)})
    failed = starting(refusing_manager(), tracking(StateName("todo")), forcing, claims)
    assert isinstance(failed.error, WorkspaceManagerError)
    assert claims.claims(IssueIdentifier.fake()).unwrap() == Claims(())


def test_a_failed_start_keeps_the_claim_this_worktree_already_held() -> None:
    tracker = tracking(StateName("todo"))
    claims = FakeClaimRegistry(
        {IssueIdentifier.fake(): Claims((Claim(id=ClaimId("ours"), holder=ours()),))}
    )
    failed = starting(refusing_manager(), tracker, StartRequest.fake(), claims)
    assert isinstance(failed.error, WorkspaceManagerError)
    assert holders(claims) == (ours(),)
