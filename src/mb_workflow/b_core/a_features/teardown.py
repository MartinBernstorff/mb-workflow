from typing import TYPE_CHECKING

from mb_workflow.b_core.c_secondary_ports.claims import LabelledClaim, release_claim
from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManagerError
from mb_workflow.b_core.d_domain_model.claim import ClaimHolder, HostName
from mb_workflow.b_core.d_domain_model.workspace import WorktreeName
from mb_workflow.d_lib.models import Model

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.claims import ClaimRegistry
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManager
    from mb_workflow.b_core.d_domain_model.config import ClaimSettings
    from mb_workflow.b_core.d_domain_model.workspace import Worktree


class TeardownRequest(Model):
    worktree: WorktreeName
    host: HostName

    @staticmethod
    def fake() -> TeardownRequest:
        return TeardownRequest(worktree=WorktreeName.fake(), host=HostName.fake())


def teardown_worktree(
    *,
    manager: WorkspaceManager,
    claims: ClaimRegistry,
    tracker: TicketTracker,
    claim_settings: ClaimSettings,
    request: TeardownRequest,
) -> None:
    worktree = manager.worktrees().named(request.worktree)
    if worktree is None:
        raise WorkspaceManagerError(f"No worktree is named {request.worktree.root}.")
    release_and_remove(
        manager=manager,
        claims=claims,
        tracker=tracker,
        claim_settings=claim_settings,
        worktree=worktree,
        host=request.host,
    )


# Release before removing, so a failed release leaves the claim beside the worktree that holds it.
# The holder is named after the ticket, as start claims it before Orca may suffix the directory.
def release_and_remove(
    *,
    manager: WorkspaceManager,
    claims: ClaimRegistry,
    tracker: TicketTracker,
    claim_settings: ClaimSettings,
    worktree: Worktree,
    host: HostName,
) -> None:
    if worktree.issue is not None:
        holder = ClaimHolder(host=host, worktree=WorktreeName.of_issue(worktree.issue))
        release_claim(
            claims,
            tracker,
            LabelledClaim(ticket=worktree.issue, holder=holder, label=claim_settings.label),
        )
    manager.remove(worktree.path)
