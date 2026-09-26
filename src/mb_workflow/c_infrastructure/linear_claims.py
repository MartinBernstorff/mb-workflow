from datetime import datetime
from typing import TYPE_CHECKING, override

from linear_python_client import LinearClient
from pydantic import AliasPath, Field

from mb_workflow.b_core.c_secondary_ports.claims import ClaimRegistry
from mb_workflow.b_core.d_domain_model.claim import (
    Claim,
    ClaimHolder,
    ClaimId,
    Claims,
    CommentBody,
)
from mb_workflow.c_infrastructure.linear import LinearApiKey, translated_errors
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


class PostedComment(Payload):
    id: ClaimId = Field(validation_alias=AliasPath("commentCreate", "comment", "id"))

    @staticmethod
    def fake() -> PostedComment:
        return PostedComment(id=ClaimId.fake())


class LinearClaims(ClaimRegistry):
    def __init__(self, client: LinearClient) -> None:
        self._client = client

    @staticmethod
    def connected(key: LinearApiKey) -> LinearClaims:
        return LinearClaims(LinearClient(api_key=key.root))

    @override
    def claims(self, ticket: IssueIdentifier) -> Claims:
        return self._thread(ticket).claims()

    @override
    def post(self, ticket: IssueIdentifier, holder: ClaimHolder) -> ClaimId:
        issue = self._thread(ticket).id
        with translated_errors():
            data = self._client.execute(
                "mutation($input: CommentCreateInput!) {"
                " commentCreate(input: $input) { success comment { id } } }",
                {"input": {"issueId": issue.root, "body": holder.comment().root}},
            )
        return PostedComment.model_validate(data).id

    @override
    def withdraw(self, ticket: IssueIdentifier, claim: ClaimId) -> None:
        with translated_errors():
            _ = self._client.execute(
                "mutation($id: String!) { commentDelete(id: $id) { success } }",
                {"id": claim.root},
            )

    def _thread(self, ticket: IssueIdentifier) -> CommentThread:
        with translated_errors():
            data = self._client.execute(
                """
                query($id: String!) {
                  issue(id: $id) {
                    id
                    comments(first: 250) { nodes { id body createdAt } }
                  }
                }
                """,
                {"id": ticket.root},
            )
        return CommentThreadRead.model_validate(data).issue
