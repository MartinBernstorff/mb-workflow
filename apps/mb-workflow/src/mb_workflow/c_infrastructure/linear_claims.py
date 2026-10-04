from datetime import datetime
from typing import TYPE_CHECKING, override

from linear_python_client import LinearClient
from pydantic import AliasPath, Field
from safe_result import Err, Ok, Result

from mb_workflow.b_core.c_secondary_ports.claims import ClaimRegistry
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTrackerError
from mb_workflow.b_core.d_domain_model.claim import (
    Claim,
    ClaimHolder,
    ClaimId,
    Claims,
    CommentBody,
)
from mb_workflow.c_infrastructure.linear import LinearApiKey, LinearCall
from mb_workflow.d_lib.models import Payload, Value

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier


class CommentedAt(Value[datetime]):
    @staticmethod
    def fake() -> CommentedAt:
        return CommentedAt(datetime.fromisoformat("2026-09-26T12:00:00Z"))


class CommentPayload(Payload):
    id: ClaimId
    body: CommentBody
    created_at: CommentedAt

    @staticmethod
    def fake() -> CommentPayload:
        return CommentPayload(
            id=ClaimId.fake(), body=CommentBody.fake(), created_at=CommentedAt.fake()
        )

    def claim(self) -> Claim | None:
        holder = ClaimHolder.parsed(self.body)
        return None if holder is None else Claim(id=self.id, holder=holder)


class IssueId(Value[str]):
    @staticmethod
    def fake() -> IssueId:
        return IssueId("7c1e3a5b-9d2f-4a6c-8e0b-3f5a7c9e1b2d")


class CommentThread(Payload):
    id: IssueId
    comments: tuple[CommentPayload, ...] = Field(
        default=(), validation_alias=AliasPath("comments", "nodes")
    )

    @staticmethod
    def fake() -> CommentThread:
        return CommentThread(id=IssueId.fake(), comments=(CommentPayload.fake(),))

    # Linear stamps comments to the millisecond, so the id breaks ties the same way for every reader.
    def claims(self) -> Claims:
        ordered = sorted(
            (comment.created_at.root, comment.id.root, claim)
            for comment in self.comments
            if (claim := comment.claim()) is not None
        )
        return Claims(tuple(claim for _, _, claim in ordered))


class CommentThreadRead(Payload):
    issue: CommentThread

    @staticmethod
    def fake() -> CommentThreadRead:
        return CommentThreadRead(issue=CommentThread.fake())


class Succeeded(Value[bool]):
    @staticmethod
    def fake() -> Succeeded:
        return Succeeded(True)


class PostedComment(Payload):
    success: Succeeded = Field(validation_alias=AliasPath("commentCreate", "success"))
    id: ClaimId | None = Field(
        default=None, validation_alias=AliasPath("commentCreate", "comment", "id")
    )

    @staticmethod
    def fake() -> PostedComment:
        return PostedComment(success=Succeeded.fake(), id=ClaimId.fake())


class DeletedComment(Payload):
    success: Succeeded = Field(validation_alias=AliasPath("commentDelete", "success"))

    @staticmethod
    def fake() -> DeletedComment:
        return DeletedComment(success=Succeeded.fake())


class LinearClaims(ClaimRegistry):
    def __init__(self, client: LinearClient) -> None:
        self._client = client

    @staticmethod
    def connected(key: LinearApiKey) -> LinearClaims:
        return LinearClaims(LinearClient(api_key=key.root))

    @override
    def claims(self, ticket: IssueIdentifier) -> Result[Claims, TicketTrackerError]:
        match self._thread(ticket):
            case Ok(thread):
                return Ok(thread.claims())
            case Err() as failed:
                return failed

    @override
    def post(self, ticket: IssueIdentifier, holder: ClaimHolder) -> ClaimId:
        # Writes still raise; MB-130 returns their errors as values too.
        issue = self._thread(ticket).unwrap().id
        with LinearCall.translated_errors():
            data = self._client.execute(
                "mutation($input: CommentCreateInput!) {"
                " commentCreate(input: $input) { success comment { id } } }",
                {"input": {"issueId": issue.root, "body": holder.comment().root}},
            )
        posted = PostedComment.model_validate(data)
        if not posted.success.root or posted.id is None:
            # lint-fixme: NoRaise
            raise TicketTrackerError(f"Linear did not post the claim on {ticket.root}.")
        return posted.id

    @override
    def withdraw(self, ticket: IssueIdentifier, claim: ClaimId) -> None:
        with LinearCall.translated_errors():
            data = self._client.execute(
                "mutation($id: String!) { commentDelete(id: $id) { success } }",
                {"id": claim.root},
            )
        if not DeletedComment.model_validate(data).success.root:
            # lint-fixme: NoRaise
            raise TicketTrackerError(f"Linear did not delete the claim {claim.root}.")

    def _thread(self, ticket: IssueIdentifier) -> Result[CommentThread, TicketTrackerError]:
        match LinearCall.answered(
            lambda: self._client.execute(
                """
                query($id: String!, $prefix: String!) {
                  issue(id: $id) {
                    id
                    comments(first: 250, filter: { body: { startsWith: $prefix } }) {
                      nodes { id body createdAt }
                    }
                  }
                }
                """,
                {"id": ticket.root, "prefix": ClaimHolder.claim_comment_prefix().root},
            )
        ):
            case Ok(data):
                return Ok(CommentThreadRead.model_validate(data).issue)
            case Err() as failed:
                return failed
