import pytest

from mb_workflow.b_core.d_domain_model.claim import (
    Claim,
    ClaimHolder,
    ClaimId,
    Claims,
    CommentBody,
    HostName,
)
from mb_workflow.b_core.d_domain_model.issue import StatusName
from mb_workflow.b_core.d_domain_model.workspace import WorktreeName


def test_a_holder_reads_back_from_its_comment() -> None:
    holder = ClaimHolder(host=HostName("ada-mbp.local"), worktree=WorktreeName("MB-34"))
    assert ClaimHolder.parsed(holder.comment()) == holder


def test_a_comment_that_is_no_claim_holds_nothing() -> None:
    assert ClaimHolder.parsed(CommentBody("Claimed by me, `MB-34` on `ada-mbp`.")) is None


def rival() -> Claim:
    return Claim(
        id=ClaimId("rival"),
        holder=ClaimHolder(host=HostName("bob-mbp"), worktree=WorktreeName.fake()),
    )


def test_the_earliest_claim_holds_the_ticket() -> None:
    assert Claims((Claim.fake(), rival())).holding(StatusName("Specced")) == Claim.fake()


def test_an_unclaimed_ticket_is_held_by_no_one() -> None:
    assert Claims(()).holding(StatusName("Specced")) is None


@pytest.mark.parametrize(
    "status", [StatusName("Merged"), StatusName("canceled"), StatusName("Duplicate")]
)
def test_a_claim_on_a_finished_ticket_is_released(status: StatusName) -> None:
    assert Claims((Claim.fake(),)).holding(status) is None
