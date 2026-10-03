from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from mb_workflow.b_core.a_features.unclaim import TicketUnclaiming
from mb_workflow.b_core.c_secondary_ports.claims import Claiming, LabelledClaim
from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManagerError
from mb_workflow.b_core.d_domain_model.claim import ClaimHolder, HostName
from mb_workflow.b_core.d_domain_model.workspace import WorktreeName
from mb_workflow.d_lib.models import Model

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.claims import ClaimRegistry
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
        TicketTracker,
        TicketTrackerError,
    )
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManager
    from mb_workflow.b_core.d_domain_model.config import ClaimSettings
    from mb_workflow.b_core.d_domain_model.workspace import Worktree


class TeardownRequest(Model):
    worktree: WorktreeName | None

    @staticmethod
    def fake() -> TeardownRequest:
        return TeardownRequest(worktree=WorktreeName.fake())


class Teardown:
    # Unclaims before removing, so a failed unclaim leaves the claim beside the worktree that holds it.
    @staticmethod
    def teardown_worktree(
        *,
        manager: WorkspaceManager,
        claims: ClaimRegistry,
        tracker: TicketTracker,
        claim_settings: ClaimSettings,
        request: TeardownRequest,
    ) -> Result[None, TicketTrackerError]:
        worktree = Teardown.targeted_worktree(manager, request.worktree)
        if worktree.issue is not None:
            unclaimed = TicketUnclaiming.unclaim_ticket(
                registry=claims,
                tracker=tracker,
                claim_settings=claim_settings,
                ticket=worktree.issue,
            )
            if isinstance(unclaimed, Err):
                return unclaimed
        manager.remove(worktree.path)
        return Ok(None)

    @staticmethod
    def targeted_worktree(manager: WorkspaceManager, name: WorktreeName | None) -> Worktree:
        if name is None:
            return manager.current()
        worktree = manager.worktrees().named(name)
        if worktree is None:
            raise WorkspaceManagerError(f"No worktree is named {name.root}.")
        return worktree

    # Release before removing, so a failed release leaves the claim beside the worktree that holds it.
    # The holder is named after the ticket, as start claims it before Orca may suffix the directory.
    @staticmethod
    def release_and_remove(
        *,
        manager: WorkspaceManager,
        claims: ClaimRegistry,
        tracker: TicketTracker,
        claim_settings: ClaimSettings,
        worktree: Worktree,
        host: HostName,
    ) -> Result[None, TicketTrackerError]:
        if worktree.issue is not None:
            holder = ClaimHolder(host=host, worktree=WorktreeName.of_issue(worktree.issue))
            released = Claiming.release_claim(
                claims,
                tracker,
                LabelledClaim(ticket=worktree.issue, holder=holder, label=claim_settings.label),
            )
            if isinstance(released, Err):
                return released
        manager.remove(worktree.path)
        return Ok(None)
