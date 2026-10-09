from typing import TYPE_CHECKING

import httpx
import pytest
import stamina
from assertions import Assert
from linear_python_client import LinearClient
from safe_result import Err, Ok

from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier, TeamKey
from mb_workflow.c_infrastructure.linear import (
    CreationLookup,
    IssueDetailRead,
    LinearApiKey,
    LinearCall,
    TeamId,
    TeamRecord,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


def test_a_creation_lookup_reads_the_named_team_apart_from_the_issue_team() -> None:
    found = CreationLookup.model_validate(
        {"team": {"nodes": [{"id": TeamId.fake().root, "key": TeamKey.fake().root}]}}
    )
    Assert.that(found.teams).matches((TeamRecord(id=TeamId.fake(), key=TeamKey.fake()),))


def test_an_issue_detail_reads_its_parent_sub_tickets_and_related_issues() -> None:
    detail = IssueDetailRead.model_validate(
        {
            "issue": {
                "identifier": "E-1",
                "title": "Add widget",
                "state": {"name": "Todo"},
                "priority": 0,
                "parent": {"identifier": "E-2"},
                "children": {"nodes": [{"identifier": "E-3"}]},
                "relations": {
                    "nodes": [{"type": "related", "relatedIssue": {"identifier": "E-4"}}]
                },
                "inverseRelations": {
                    "nodes": [{"type": "related", "issue": {"identifier": "E-5"}}]
                },
            }
        }
    ).issue.detail()
    Assert.that((detail.parent, detail.sub_tickets, detail.related)).matches(
        (
            IssueIdentifier("E-2"),
            frozenset({IssueIdentifier("E-3")}),
            frozenset({IssueIdentifier("E-4"), IssueIdentifier("E-5")}),
        )
    )


class FlakyServer:
    # Answers with a 5xx for its first `failures` requests, then succeeds.
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.requests = 0

    def __call__(self, _request: httpx.Request) -> httpx.Response:
        self.requests += 1
        if self.requests <= self.failures:
            return httpx.Response(502, text="Bad Gateway")
        return httpx.Response(200, json={"data": {"viewer": {"id": "U-1"}}})

    def client(self) -> LinearClient:
        return LinearClient(
            api_key=LinearApiKey.fake().root,
            http_client=httpx.Client(transport=httpx.MockTransport(self)),
        )


@pytest.fixture(autouse=True)
def _no_backoff() -> Iterator[None]:
    with stamina.set_testing(True, attempts=10, cap=True):
        yield


def test_a_call_that_hits_transient_server_errors_is_retried_until_it_succeeds() -> None:
    server = FlakyServer(failures=2)
    client = server.client()
    answered = LinearCall.answered(lambda: client.execute("query { viewer { id } }"))
    Assert.that((answered, server.requests)).matches((Ok({"viewer": {"id": "U-1"}}), 3))


def test_a_call_that_keeps_hitting_server_errors_gives_up_after_three_attempts() -> None:
    server = FlakyServer(failures=3)
    client = server.client()
    answered = LinearCall.answered(lambda: client.execute("query { viewer { id } }"))
    Assert.that((isinstance(answered, Err), server.requests)).matches((True, 3))
