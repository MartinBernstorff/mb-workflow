from assertions import Assert

from mb_workflow.b_core.d_domain_model.issue import TeamKey
from mb_workflow.c_infrastructure.linear import CreationLookup, TeamId, TeamRecord


def test_a_creation_lookup_reads_the_named_team_apart_from_the_issue_team() -> None:
    found = CreationLookup.model_validate(
        {"team": {"nodes": [{"id": TeamId.fake().root, "key": TeamKey.fake().root}]}}
    )
    Assert.that(found.teams).matches((TeamRecord(id=TeamId.fake(), key=TeamKey.fake()),))
