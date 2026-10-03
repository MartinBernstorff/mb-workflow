import re

import pytest

from mb_workflow.b_core.a_features.link import AlreadyLinkedError, LinkRequest, TicketLinking
from mb_workflow.b_core.c_secondary_ports.claims import ClaimRefusedError, FakeClaimRegistry
from mb_workflow.b_core.c_secondary_ports.status import FakeStatusStore
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import FakeTicketTracker, TrackedIssue
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
from mb_workflow.b_core.d_domain_model.flow import FlowError, StateName, StateNames, WorkflowChart
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
from mb_workflow.b_core.d_domain_model.issue import (
    Assigned,
    Assignee,
    Issue,
    IssueIdentifier,
    IssueTitle,
    LabelName,
    LabelNames,
)
from mb_workflow.b_core.d_domain_model.workspace import (
    DisplayName,
    RepoId,
    WorkspaceStatuses,
    Worktree,
    WorktreeName,
    WorktreePath,
    Worktrees,
)


def tracking(state: StateName | None) -> FakeTicketTracker:
    flow = () if state is None else (LabelName(state.root),)
    issue = Issue.fake().model_copy(update={"labels": LabelNames((*LabelNames.fake().root, *flow))})
    return FakeTicketTracker(
        LabelNames((*LabelNames.fake().root, LabelName("claimed"), *FlowLabels.fake().labels.root)),
        (TrackedIssue.fake().model_copy(update={"issue": issue}),),
        groups={FlowLabels.fake().group: FlowLabels.fake().labels},
    )


def fake_board() -> FakeStatusStore:
    return FakeStatusStore(StateName.fake())


def fake_board_statuses() -> WorkspaceStatuses:
    return WorkspaceStatuses(
        tuple(fake_board().status_for(state) for state in StateNames.of_chart(WorkflowChart).root)
    )


# The current worktree's directory is not named after the ticket, as when made outside mw start.
def here_linked_to(issue: IssueIdentifier | None) -> Worktrees:
    here = Worktree.bare(RepoId.fake(), WorktreePath.fake()).model_copy(update={"issue": issue})
    return Worktrees((here,))


def managing(worktrees: Worktrees) -> FakeWorkspaceManager:
    return FakeWorkspaceManager(worktrees, WorktreePath.fake(), fake_board_statuses())


def linking(
    manager: FakeWorkspaceManager,
    tracker: FakeTicketTracker,
    claims: FakeClaimRegistry,
    request: LinkRequest,
    *,
    workspace: WorkspaceSettings | None = None,
) -> None:
    TicketLinking.link_ticket(
        manager=manager,
        tracker=tracker,
        claims=claims,
        board=fake_board(),
        workspace=workspace or WorkspaceSettings.fake(),
        claim_settings=ClaimSettings.fake(),
        flow_labels=FlowLabels.fake(),
        request=request,
    )


def linked(state: StateName | None, request: LinkRequest) -> Worktree:
    manager = managing(here_linked_to(None))
    linking(manager, tracking(state), FakeClaimRegistry(), request)
    return manager.current()


def forcing() -> LinkRequest:
    return LinkRequest.fake().model_copy(update={"take_over": TakeOver(True)})


def our_holder() -> ClaimHolder:
    return ClaimHolder(
        host=LinkRequest.fake().host, worktree=WorktreeName.of_issue(IssueIdentifier.fake())
    )


def claimed_by(holder: ClaimHolder, ticket: IssueIdentifier) -> FakeClaimRegistry:
    return FakeClaimRegistry({ticket: Claims((Claim(id=ClaimId.fake(), holder=holder),))})


def claimed_by_host(host: HostName) -> FakeClaimRegistry:
    rival = ClaimHolder(host=host, worktree=WorktreeName.of_issue(IssueIdentifier.fake()))
    return claimed_by(rival, IssueIdentifier.fake())


def holders(claims: FakeClaimRegistry, ticket: IssueIdentifier) -> tuple[ClaimHolder, ...]:
    return tuple(claim.holder for claim in claims.claims(ticket).root)


def test_links_the_current_worktree_to_the_ticket() -> None:
    assert linked(StateName.fake(), LinkRequest.fake()).issue == IssueIdentifier.fake()


def test_names_the_current_worktree_after_the_ticket_title() -> None:
    linked_here = linked(StateName.fake(), LinkRequest.fake())
    assert linked_here.display_name == DisplayName.of_issue(IssueTitle.fake())


def test_moves_the_current_worktree_to_the_column_of_the_flow_state() -> None:
    state = StateName.fake()
    linked_here = linked(state, LinkRequest.fake())
    assert linked_here.status == fake_board().status_for(state)


def test_a_refused_display_name_still_links_the_worktree() -> None:
    manager = DisplayNameRefusingWorkspaceManager(
        here_linked_to(None), WorktreePath.fake(), fake_board_statuses()
    )
    linking(manager, tracking(StateName.fake()), FakeClaimRegistry(), LinkRequest.fake())
    assert manager.current().issue == IssueIdentifier.fake()


# Teardown and drain rebuild the holder from the ticket, so the directory name must not leak in.
def test_claims_the_ticket_under_the_tickets_name() -> None:
    claims = FakeClaimRegistry()
    linking(managing(here_linked_to(None)), tracking(StateName.fake()), claims, LinkRequest.fake())
    assert holders(claims, IssueIdentifier.fake()) == (our_holder(),)


def test_the_linked_ticket_carries_the_claim_label() -> None:
    tracker = tracking(StateName.fake())
    linking(managing(here_linked_to(None)), tracker, FakeClaimRegistry(), LinkRequest.fake())
    labels = tracker.read_issue(IssueIdentifier.fake()).labels
    assert labels.has(ClaimSettings.fake().label).root


def test_assigns_the_ticket_to_the_configured_assignee() -> None:
    tracker = tracking(StateName.fake())
    assignee = Assignee("other@flowbase.io")
    workspace = WorkspaceSettings.fake().model_copy(update={"assignee": assignee})
    linking(
        managing(here_linked_to(None)),
        tracker,
        FakeClaimRegistry(),
        LinkRequest.fake(),
        workspace=workspace,
    )
    assert tracker.read_issue_detail(IssueIdentifier.fake()).assignee == assignee


def test_relinking_the_ticket_already_linked_keeps_a_single_claim() -> None:
    claims = claimed_by(our_holder(), IssueIdentifier.fake())
    manager = managing(here_linked_to(IssueIdentifier.fake()))
    linking(manager, tracking(StateName.fake()), claims, LinkRequest.fake())
    assert holders(claims, IssueIdentifier.fake()) == (our_holder(),)
    assert manager.current().issue == IssueIdentifier.fake()


def test_a_ticket_without_a_flow_label_is_neither_claimed_nor_linked() -> None:
    manager = managing(here_linked_to(None))
    tracker = tracking(None)
    claims = FakeClaimRegistry()
    with pytest.raises(FlowError, match="no flow label"):
        linking(manager, tracker, claims, LinkRequest.fake())
    assert manager.current().issue is None
    assert claims.claims(IssueIdentifier.fake()) == Claims(())
    assert tracker.read_issue(IssueIdentifier.fake()).assigned == Assigned(False)


def test_a_ticket_claimed_by_another_host_is_not_linked() -> None:
    rival = HostName("bob-mbp.local")
    manager = managing(here_linked_to(None))
    with pytest.raises(ClaimRefusedError, match=re.escape(rival.root)):
        linking(manager, tracking(StateName.fake()), claimed_by_host(rival), LinkRequest.fake())
    assert manager.current().issue is None


def test_force_takes_the_claim_over_from_another_host() -> None:
    manager = managing(here_linked_to(None))
    claims = claimed_by_host(HostName("bob-mbp.local"))
    linking(manager, tracking(StateName.fake()), claims, forcing())
    assert holders(claims, IssueIdentifier.fake()) == (our_holder(),)
    assert manager.current().issue == IssueIdentifier.fake()


def test_a_worktree_linked_to_another_ticket_is_neither_relinked_nor_claimed() -> None:
    previous = IssueIdentifier("E-1")
    manager = managing(here_linked_to(previous))
    claims = FakeClaimRegistry()
    with pytest.raises(AlreadyLinkedError, match=previous.root):
        linking(manager, tracking(StateName.fake()), claims, LinkRequest.fake())
    assert manager.current().issue == previous
    assert claims.claims(IssueIdentifier.fake()) == Claims(())


def test_force_replaces_the_link_to_another_ticket() -> None:
    manager = managing(here_linked_to(IssueIdentifier("E-1")))
    linking(manager, tracking(StateName.fake()), FakeClaimRegistry(), forcing())
    assert manager.current().issue == IssueIdentifier.fake()


def test_force_leaves_the_previous_tickets_claim_alone() -> None:
    previous = IssueIdentifier("E-1")
    previous_holder = ClaimHolder(
        host=LinkRequest.fake().host, worktree=WorktreeName.of_issue(previous)
    )
    claims = claimed_by(previous_holder, previous)
    linking(managing(here_linked_to(previous)), tracking(StateName.fake()), claims, forcing())
    assert holders(claims, previous) == (previous_holder,)
