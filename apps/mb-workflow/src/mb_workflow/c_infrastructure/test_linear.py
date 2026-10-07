from assertions import Assert

from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier, TeamKey
from mb_workflow.c_infrastructure.linear import (
    CreationLookup,
    IssueDetailRead,
    TeamId,
    TeamRecord,
)


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
