from typing import override

from assertions import Assert
from safe_result import Ok, Result

from mb_workflow.b_core.c_secondary_ports.claims import (
    Claiming,
    ClaimLostError,
    ClaimRefusedError,
    ClaimRequest,
    FakeClaimRegistry,
    LabelledClaim,
)
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
    FakeTicketTracker,
    TicketTrackerError,
    TrackedIssue,
)
from mb_workflow.b_core.d_domain_model.claim import (
    Claim,
    ClaimHolder,
    ClaimId,
    Claims,
    HostName,
    Posted,
    TakeOver,
)
from mb_workflow.b_core.d_domain_model.issue import (
    Issue,
    IssueIdentifier,
    LabelName,
    LabelNames,
)


def tracker_with_the_claimed_label() -> FakeTicketTracker:
    issue = Issue.fake().model_copy(
        update={"labels": LabelNames((*Issue.fake().labels.root, LabelName("claimed")))}
    )
    return FakeTicketTracker(
        LabelNames((*LabelNames.fake().root, LabelName("claimed"))),
        (TrackedIssue.fake().model_copy(update={"issue": issue}),),
    )


def rival() -> ClaimHolder:
    return ClaimHolder.fake().model_copy(update={"host": HostName("bob-mbp.local")})


def registry_held_by(*holders: ClaimHolder) -> FakeClaimRegistry:
    return FakeClaimRegistry(
        {
            IssueIdentifier.fake(): Claims(
                tuple(
                    Claim(id=ClaimId(f"held-{index}"), holder=holder)
                    for index, holder in enumerate(holders)
                )
            )
        }
    )


def claim_holders(registry: FakeClaimRegistry) -> tuple[ClaimHolder, ...]:
    return tuple(claim.holder for claim in registry.claims(IssueIdentifier.fake()).unwrap().root)


def test_releasing_withdraws_the_holders_claim() -> None:
    registry = registry_held_by(ClaimHolder.fake())
    Claiming.release_claim(
        registry, tracker_with_the_claimed_label(), LabelledClaim.fake()
    ).unwrap()
    Assert.that(registry.claims(IssueIdentifier.fake()).unwrap()).matches(Claims(()))


def test_releasing_the_last_claim_removes_the_label() -> None:
    tracker = tracker_with_the_claimed_label()
    labelled = LabelledClaim.fake().model_copy(update={"label": LabelName("claimed")})
    Claiming.release_claim(registry_held_by(ClaimHolder.fake()), tracker, labelled).unwrap()
    Assert.that(tracker.read_issue(IssueIdentifier.fake()).unwrap().labels).matches(
        Issue.fake().labels
    )


def test_releasing_leaves_another_holders_claim_and_its_label() -> None:
    registry = registry_held_by(rival())
    tracker = tracker_with_the_claimed_label()
    Claiming.release_claim(registry, tracker, LabelledClaim.fake()).unwrap()
    Assert.that(claim_holders(registry)).matches((rival(),))
    Assert.that(
        tracker.read_issue(IssueIdentifier.fake()).unwrap().labels.has(LabelName("claimed")).root
    ).is_true()


def test_releasing_keeps_the_label_while_another_claim_remains() -> None:
    registry = registry_held_by(ClaimHolder.fake(), rival())
    tracker = tracker_with_the_claimed_label()
    Claiming.release_claim(registry, tracker, LabelledClaim.fake()).unwrap()
    Assert.that(claim_holders(registry)).matches((rival(),))
    Assert.that(
        tracker.read_issue(IssueIdentifier.fake()).unwrap().labels.has(LabelName("claimed")).root
    ).is_true()


def test_labelling_a_claim_adds_the_label() -> None:
    tracker = FakeTicketTracker(
        LabelNames((*LabelNames.fake().root, LabelName("claimed"))), (TrackedIssue.fake(),)
    )
    _ = Claiming.label_claim(tracker, LabelledClaim.fake())
    Assert.that(
        tracker.read_issue(IssueIdentifier.fake()).unwrap().labels.has(LabelName("claimed")).root
    ).is_true()


def test_a_label_the_tracker_lacks_refuses_the_claim() -> None:
    tracker = FakeTicketTracker(LabelNames.fake(), (TrackedIssue.fake(),))
    labelled = Claiming.label_claim(tracker, LabelledClaim.fake())
    _ = Assert.that(labelled.error).is_instance(ClaimRefusedError)
    Assert.that(tracker.read_issue(IssueIdentifier.fake()).unwrap().labels).matches(
        TrackedIssue.fake().issue.labels
    )


def test_claiming_a_ticket_another_holder_holds_is_refused_as_lost() -> None:
    registry = registry_held_by(rival())
    claimed = Claiming.claim_ticket(registry, ClaimRequest.fake())
    _ = Assert.that(claimed.error).is_instance(ClaimLostError)
    Assert.that(claim_holders(registry)).matches((rival(),))


def test_taking_over_a_claim_replaces_the_other_holders_claim() -> None:
    registry = registry_held_by(rival())
    taking_over = ClaimRequest.fake().model_copy(update={"take_over": TakeOver(True)})
    Assert.that(Claiming.claim_ticket(registry, taking_over)).matches(Ok(Posted(True)))
    Assert.that(claim_holders(registry)).matches((ClaimHolder.fake(),))


class WithdrawingRegistry(FakeClaimRegistry):
    @override
    def post(
        self, ticket: IssueIdentifier, holder: ClaimHolder
    ) -> Result[ClaimId, TicketTrackerError]:
        posted = super().post(ticket, holder)
        for claim in self.claims(ticket).unwrap().root:
            _ = super().withdraw(ticket, claim.id)
        return posted


def test_a_claim_withdrawn_by_another_is_returned_as_lost() -> None:
    registry = WithdrawingRegistry()
    claimed = Claiming.claim_ticket(registry, ClaimRequest.fake())
    _ = Assert.that(claimed.error).is_instance(ClaimLostError)
    Assert.that(claim_holders(registry)).matches(())
