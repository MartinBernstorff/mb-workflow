import re
import socket

from mb_workflow.b_core.d_domain_model.flow import WorkflowChart
from mb_workflow.b_core.d_domain_model.issue import (
    IssueStatusName,
    StatusNames,
    StatusType,
    StatusTypes,
)
from mb_workflow.b_core.d_domain_model.workspace import WorktreeName
from mb_workflow.d_lib.models import Model, Value


class HostName(Value[str]):
    @staticmethod
    def fake() -> HostName:
        return HostName("ada-mbp.local")

    @staticmethod
    def of_machine() -> HostName:
        return HostName(socket.gethostname())


class CommentBody(Value[str]):
    @staticmethod
    def fake() -> CommentBody:
        return ClaimHolder.fake().comment()


class ClaimHolder(Model):
    host: HostName
    worktree: WorktreeName

    @staticmethod
    def fake() -> ClaimHolder:
        return ClaimHolder(host=HostName.fake(), worktree=WorktreeName.fake())

    @staticmethod
    def claim_comment_prefix() -> CommentBody:
        return CommentBody("Claimed by mw from worktree")

    @staticmethod
    def parsed(body: CommentBody) -> ClaimHolder | None:
        found = re.fullmatch(
            re.escape(ClaimHolder.claim_comment_prefix().root)
            + r" `(?P<worktree>[^`]+)` on host `(?P<host>[^`]+)`\.",
            body.root.strip(),
        )
        if found is None:
            return None
        return ClaimHolder(host=HostName(found["host"]), worktree=WorktreeName(found["worktree"]))

    def comment(self) -> CommentBody:
        return CommentBody(
            f"{ClaimHolder.claim_comment_prefix().root} `{self.worktree.root}`"
            f" on host `{self.host.root}`."
        )


class ClaimId(Value[str]):
    @staticmethod
    def fake() -> ClaimId:
        return ClaimId("2f1c6a3e-8b4d-4e5f-9a0b-1c2d3e4f5a6b")


class Claim(Model):
    id: ClaimId
    holder: ClaimHolder

    @staticmethod
    def fake() -> Claim:
        return Claim(id=ClaimId.fake(), holder=ClaimHolder.fake())


# Earliest first, so every claimer reading the ticket agrees on who holds it.
class Claims(Value[tuple[Claim, ...]]):
    @staticmethod
    def fake() -> Claims:
        return Claims((Claim.fake(),))

    def holding(self, status: IssueStatusName) -> Claim | None:
        if Released.of(status).root:
            return None
        return self.root[0] if self.root else None

    def ids(self) -> tuple[ClaimId, ...]:
        return tuple(claim.id for claim in self.root)


class Released(Value[bool]):
    @staticmethod
    def fake() -> Released:
        return Released(False)

    @staticmethod
    def statuses() -> StatusNames:
        merged = tuple(IssueStatusName(state.name) for state in WorkflowChart.final_states)
        return StatusNames((*StatusNames.closed().root, *merged))

    @staticmethod
    def of(status: IssueStatusName) -> Released:
        return Released(Released.statuses().matching(status) is not None)

    @staticmethod
    def of_type(status_type: StatusType) -> Released:
        return Released(status_type in (StatusType.completed, StatusType.canceled))

    @staticmethod
    def types() -> StatusTypes:
        return StatusTypes(tuple(kind for kind in StatusType if Released.of_type(kind).root))


# Whether claiming posted a new claim, rather than finding this holder's claim already there.
class Posted(Value[bool]):
    @staticmethod
    def fake() -> Posted:
        return Posted(True)


class TakeOver(Value[bool]):
    @staticmethod
    def fake() -> TakeOver:
        return TakeOver(False)
