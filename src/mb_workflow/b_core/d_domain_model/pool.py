from enum import IntEnum

from mb_workflow.b_core.d_domain_model.issue import (
    Issue,
    IssueIdentifier,
    IssueStatusName,
    LabelName,
    LabelNames,
    StatusNames,
)
from mb_workflow.d_lib.models import Model, Value


class ViewSlug(Value[str]):
    @staticmethod
    def fake() -> ViewSlug:
        return ViewSlug("4efb86b38740")


# Numbered as Linear numbers them, so a view's tickets read their priority without translation.
class Priority(IntEnum):
    no_priority = 0
    urgent = 1
    high = 2
    medium = 3
    low = 4


class Ready(Value[bool]):
    @staticmethod
    def fake() -> Ready:
        return Ready(True)


class Resolved(Value[bool]):
    @staticmethod
    def fake() -> Resolved:
        return Resolved(True)


class Blocker(Model):
    issue: IssueIdentifier
    status: IssueStatusName

    @staticmethod
    def fake() -> Blocker:
        return Blocker(issue=IssueIdentifier("MB-7"), status=IssueStatusName("Merged"))

    @staticmethod
    def resolved_statuses() -> StatusNames:
        return StatusNames((IssueStatusName("Merged"), *StatusNames.closed().root))

    def resolved(self) -> Resolved:
        return Resolved(Blocker.resolved_statuses().matching(self.status) is not None)


class Blockers(Value[tuple[Blocker, ...]]):
    @staticmethod
    def fake() -> Blockers:
        return Blockers((Blocker.fake(),))

    def unresolved(self) -> Blockers:
        return Blockers(tuple(blocker for blocker in self.root if not blocker.resolved().root))


class PoolTicket(Model):
    issue: Issue
    priority: Priority
    blockers: Blockers

    @staticmethod
    def fake() -> PoolTicket:
        return PoolTicket(
            issue=Issue.fake().model_copy(
                update={"status": IssueStatusName("Specced"), "labels": LabelNames(())}
            ),
            priority=Priority.medium,
            blockers=Blockers.fake(),
        )

    @staticmethod
    def ready_statuses() -> StatusNames:
        return StatusNames(
            tuple(
                IssueStatusName(name) for name in ("Grilling", "Specced", "Implementing", "Merging")
            )
        )

    def ready(self, claim_label: LabelName) -> Ready:
        return Ready(
            PoolTicket.ready_statuses().matching(self.issue.status) is not None
            and self.issue.labels.matching(claim_label) is None
            and not self.blockers.unresolved().root
        )


class PoolTickets(Value[tuple[PoolTicket, ...]]):
    @staticmethod
    def fake() -> PoolTickets:
        return PoolTickets((PoolTicket.fake(),))

    def ready(self, claim_label: LabelName) -> PoolTickets:
        return PoolTickets(tuple(ticket for ticket in self.root if ticket.ready(claim_label).root))

    def identifiers(self) -> tuple[IssueIdentifier, ...]:
        return tuple(ticket.issue.identifier for ticket in self.root)
