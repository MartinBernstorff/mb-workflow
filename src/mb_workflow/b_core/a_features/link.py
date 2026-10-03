import logging
from typing import TYPE_CHECKING

from mb_workflow.b_core.a_features.start import action_in
from mb_workflow.b_core.b_domain_services.take_ticket import take_ticket
from mb_workflow.b_core.c_secondary_ports.claims import ClaimRequest
from mb_workflow.b_core.c_secondary_ports.workspace_manager import set_display_name_or_warn
from mb_workflow.b_core.d_domain_model.claim import ClaimHolder, HostName, TakeOver
from mb_workflow.b_core.d_domain_model.flow import FlowError, WorkflowChart
from mb_workflow.b_core.d_domain_model.flow_labels import state_of
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
from mb_workflow.b_core.d_domain_model.workspace import DisplayName, WorktreeName
from mb_workflow.d_lib.models import Model

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.claims import ClaimRegistry
    from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManager
    from mb_workflow.b_core.d_domain_model.config import ClaimSettings, WorkspaceSettings
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.workspace import Worktree

logger = logging.getLogger(__name__)


class AlreadyLinkedError(Exception):
    pass


class LinkRequest(Model):
    ticket: IssueIdentifier
    host: HostName
    # Takes the claim over from other hosts and replaces a link to another ticket.
    take_over: TakeOver

    @staticmethod
    def fake() -> LinkRequest:
        return LinkRequest(
            ticket=IssueIdentifier.fake(), host=HostName.fake(), take_over=TakeOver.fake()
        )


# Does what start does for a worktree that already exists, minus typing the prompt.
def link_ticket(
    *,
    manager: WorkspaceManager,
    tracker: TicketTracker,
    claims: ClaimRegistry,
    board: WorkspaceStatusStore,
    workspace: WorkspaceSettings,
    claim_settings: ClaimSettings,
    flow_labels: FlowLabels,
    request: LinkRequest,
) -> None:
    # Resolve the state and refuse before touching anything, so a refused link leaves no claim behind.
    detail = tracker.read_issue_detail(request.ticket)
    state = state_of(WorkflowChart, flow_labels, detail.issue.grouped)
    if state is None:
        raise FlowError(f"{request.ticket.root} carries no flow label, so it is not in the flow.")
    _ = action_in(request.ticket, state)
    here = manager.current()
    require_unlinked_or_forced(here, request)

    # Named after the ticket, not the directory, as teardown and drain rebuild the holder that way.
    take_ticket(
        claims=claims,
        tracker=tracker,
        workspace=workspace,
        claim_settings=claim_settings,
        request=ClaimRequest(
            ticket=request.ticket,
            status=detail.issue.status,
            holder=ClaimHolder(host=request.host, worktree=WorktreeName.of_issue(request.ticket)),
            take_over=request.take_over,
        ),
    )

    manager.set_linked_issue(here.path, request.ticket)
    logger.info("Linked %s to %s.", here.path.root, request.ticket.root)
    manager.set_status(here.path, board.status_for(state))
    set_display_name_or_warn(manager, here.path, DisplayName.of_issue(detail.title))


# The previous ticket's claim is left alone, as this worktree may not be the one holding it.
def require_unlinked_or_forced(here: Worktree, request: LinkRequest) -> None:
    if here.issue is None or here.issue == request.ticket:
        return
    if not request.take_over.root:
        raise AlreadyLinkedError(
            f"{here.path.root} is linked to {here.issue.root}. Pass --force to link it to"
            f" {request.ticket.root} instead."
        )
    logger.warning(
        "Replacing the link from %s to %s; its claim is left in place.",
        here.issue.root,
        request.ticket.root,
    )
