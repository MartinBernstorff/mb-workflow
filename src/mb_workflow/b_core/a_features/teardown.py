from typing import TYPE_CHECKING

from mb_workflow.b_core.c_secondary_ports.claims import release_claim
from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManagerError
from mb_workflow.b_core.d_domain_model.claim import ClaimHolder, HostName
from mb_workflow.b_core.d_domain_model.workspace import WorktreeName
from mb_workflow.d_lib.models import Model

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.claims import ClaimRegistry
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManager
    from mb_workflow.b_core.d_domain_model.workspace import Worktree


class TeardownRequest(Model):
    worktree: WorktreeName
    host: HostName

    @staticmethod
    def fake() -> TeardownRequest:
        return TeardownRequest(worktree=WorktreeName.fake(), host=HostName.fake())


def teardown_worktree(
    *, manager: WorkspaceManager, claims: ClaimRegistry, request: TeardownRequest
) -> None:
    worktree = manager.worktrees().named(request.worktree)
    if worktree is None:
        raise WorkspaceManagerError(f"No worktree is named {request.worktree.root}.")
    tear_down(manager, claims, worktree, request.host)


# Release before removing, so a failed release leaves the claim beside the worktree that holds it.
def tear_down(
    manager: WorkspaceManager, claims: ClaimRegistry, worktree: Worktree, host: HostName
) -> None:
    if worktree.issue is not None:
        release_claim(claims, worktree.issue, ClaimHolder(host=host, worktree=worktree.path.name()))
    manager.remove(worktree.path)
