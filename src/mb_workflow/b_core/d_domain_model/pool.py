from enum import IntEnum

from pydantic import Field, JsonValue, NonNegativeInt, field_validator, model_validator

from mb_workflow.b_core.d_domain_model.flow import StateNames, WorkflowChart
from mb_workflow.b_core.d_domain_model.issue import (
    Issue,
    IssueIdentifier,
    Issues,
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
                IssueStatusName(name)
                for name in (
                    "Backlog",
                    "Grilling",
                    "Speccing",
                    "Specced",
                    "Implementing",
                    "Merging",
                )
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


class Limit(Value[NonNegativeInt]):
    @staticmethod
    def fake() -> Limit:
        return Limit(4)


class Admitted(Value[bool]):
    @staticmethod
    def fake() -> Admitted:
        return Admitted(True)


class Filled(Value[bool]):
    @staticmethod
    def fake() -> Filled:
        return Filled(False)


class TicketCount(Value[NonNegativeInt]):
    @staticmethod
    def fake() -> TicketCount:
        return TicketCount(1)


class Occupancy(Value[tuple[IssueStatusName, ...]]):
    @staticmethod
    def fake() -> Occupancy:
        return Occupancy((IssueStatusName("Implementing"),))

    @staticmethod
    def of(issues: Issues) -> Occupancy:
        return Occupancy(tuple(issue.status for issue in issues.root))

    def with_ticket_in(self, status: IssueStatusName) -> Occupancy:
        return Occupancy((*self.root, status))

    def count_in(self, status: IssueStatusName) -> TicketCount:
        return TicketCount(sum(1 for held in self.root if held.names(status).root))


class LimitSummary(Value[str]):
    @staticmethod
    def fake() -> LimitSummary:
        return LimitSummary("total 4, Grilling 1")


def default_status_limits() -> dict[IssueStatusName, Limit]:
    return {IssueStatusName("Grilling"): Limit(1)}


def chart_statuses() -> StatusNames:
    return StatusNames(
        tuple(IssueStatusName(state.root) for state in StateNames.of_chart(WorkflowChart).root)
    )


class PoolLimits(Model):
    total: Limit = Limit(4)
    statuses: dict[IssueStatusName, Limit] = Field(default_factory=default_status_limits)

    @staticmethod
    def fake() -> PoolLimits:
        return PoolLimits()

    # [pool.limits] lists status limits flat beside total, and they only override the defaults.
    @model_validator(mode="before")
    @classmethod
    def gather_status_limits(cls, data: JsonValue) -> JsonValue:
        if not isinstance(data, dict) or "statuses" in data:
            return data
        statuses: dict[str, JsonValue] = {
            name.root: limit.root for name, limit in default_status_limits().items()
        }
        statuses.update({key: limit for key, limit in data.items() if key != "total"})
        return {**{key: data[key] for key in ("total",) if key in data}, "statuses": statuses}

    @field_validator("statuses")
    @classmethod
    def spell_as_the_chart(
        cls, statuses: dict[IssueStatusName, Limit]
    ) -> dict[IssueStatusName, Limit]:
        chart = chart_statuses()
        spelled: dict[IssueStatusName, Limit] = {}
        for name, limit in statuses.items():
            known = chart.matching(name)
            if known is None:
                listed = ", ".join(sorted(status.root for status in chart.root))
                raise ValueError(
                    f"{name.root} is not a status in the chart. Limit one of {listed}."
                )
            spelled[known] = limit
        return spelled

    def summary(self) -> LimitSummary:
        return LimitSummary(
            ", ".join(
                (
                    f"total {self.total.root}",
                    *(f"{name.root} {limit.root}" for name, limit in self.statuses.items()),
                )
            )
        )

    def filled(self, occupancy: Occupancy) -> Filled:
        return Filled(len(occupancy.root) >= self.total.root)

    def admits(self, occupancy: Occupancy, status: IssueStatusName) -> Admitted:
        if self.filled(occupancy).root:
            return Admitted(False)
        limit = next(
            (held for name, held in self.statuses.items() if name.names(status).root), None
        )
        return Admitted(limit is None or occupancy.count_in(status).root < limit.root)
