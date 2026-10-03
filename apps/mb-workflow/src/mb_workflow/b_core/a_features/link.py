import logging
from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from mb_workflow.b_core.b_domain_services.next_action import TicketState
from mb_workflow.b_core.b_domain_services.take_ticket import TicketTaking
from mb_workflow.b_core.c_secondary_ports.claims import ClaimRequest
from mb_workflow.b_core.c_secondary_ports.workspace_manager import set_display_name_or_warn
from mb_workflow.b_core.d_domain_model.claim import ClaimHolder, HostName, TakeOver
from mb_workflow.b_core.d_domain_model.flow import FlowError, WorkflowChart
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

    # The previous ticket's claim is left alone, as this worktree may not be the one holding it.
    def require_unlinked_or_forced(self, here: Worktree) -> None:
        if here.issue is None or here.issue == self.ticket:
            return
        if not self.take_over.root:
            raise AlreadyLinkedError(
                f"{here.path.root} is linked to {here.issue.root}. Pass --force to link it to"
                f" {self.ticket.root} instead."
            )
        logger.warning(
            "Replacing the link from %s to %s; its claim is left in place.",
            here.issue.root,
            self.ticket.root,
        )


class TicketLinking:
    # Does what start does for a worktree that already exists, minus typing the prompt.
    @staticmethod
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
    ) -> Result[None, FlowError]:
        # Refuse before touching anything, so a refused link leaves no claim behind.
        detail = tracker.read_issue_detail(request.ticket)
        with_work_left = TicketState.state_with_work_left(WorkflowChart, flow_labels, detail.issue)
        if isinstance(with_work_left, Err):
            return with_work_left
        state = with_work_left.value
        here = manager.current()
        request.require_unlinked_or_forced(here)

        # Named after the ticket, not the directory, as teardown and drain rebuild the holder that way.
        TicketTaking.take_ticket(
            claims=claims,
            tracker=tracker,
            workspace=workspace,
            claim_settings=claim_settings,
            request=ClaimRequest(
                ticket=request.ticket,
                status=detail.issue.status,
                holder=ClaimHolder(
                    host=request.host, worktree=WorktreeName.of_issue(request.ticket)
                ),
                take_over=request.take_over,
            ),
            previous=detail.assignee,
        )

        manager.set_linked_issue(here.path, request.ticket)
        logger.info("Linked %s to %s.", here.path.root, request.ticket.root)
        manager.set_status(here.path, board.status_for(state))
        set_display_name_or_warn(manager, here.path, DisplayName.of_issue(detail.title))
        return Ok(None)
