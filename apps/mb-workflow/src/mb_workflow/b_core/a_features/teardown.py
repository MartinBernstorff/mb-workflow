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
    @staticmethod
    def teardown_worktree(
        *,
        manager: WorkspaceManager,
        claims: ClaimRegistry,
        tracker: TicketTracker,
        claim_settings: ClaimSettings,
        request: TeardownRequest,
    ) -> Result[None, TicketTrackerError | WorkspaceManagerError]:
        targeted = Teardown.targeted_worktree(manager, request.worktree)
        if isinstance(targeted, Err):
            return targeted
        worktree = targeted.value
        if worktree.issue is not None:
            unclaimed = TicketUnclaiming.unclaim_ticket(
                registry=claims,
                tracker=tracker,
                claim_settings=claim_settings,
                ticket=worktree.issue,
            )
            if isinstance(unclaimed, Err):
                return unclaimed
        return manager.remove(worktree.path)

    @staticmethod
    def targeted_worktree(
        manager: WorkspaceManager, name: WorktreeName | None
    ) -> Result[Worktree, WorkspaceManagerError]:
        if name is None:
            return manager.current()
        listed = manager.worktrees()
        if isinstance(listed, Err):
            return listed
        worktree = listed.value.named(name)
        if worktree is None:
            return Err(WorkspaceManagerError(f"No worktree is named {name.root}."))
        return Ok(worktree)

    @staticmethod
    def release_and_remove(
        *,
        manager: WorkspaceManager,
        claims: ClaimRegistry,
        tracker: TicketTracker,
        claim_settings: ClaimSettings,
        worktree: Worktree,
        host: HostName,
    ) -> Result[None, TicketTrackerError | WorkspaceManagerError]:
        if worktree.issue is not None:
            holder = ClaimHolder(host=host, worktree=WorktreeName.of_issue(worktree.issue))
            released = Claiming.release_claim(
                claims,
                tracker,
                LabelledClaim(ticket=worktree.issue, holder=holder, label=claim_settings.label),
            )
            if isinstance(released, Err):
                return released
        return manager.remove(worktree.path)
