from enum import IntEnum

from pydantic import Field, JsonValue, NonNegativeInt, model_validator

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


class PoolTicket(Model):
    issue: Issue
    priority: Priority

    @staticmethod
    def fake() -> PoolTicket:
        return PoolTicket(
            issue=Issue.fake().model_copy(
                update={"status": IssueStatusName("Specced"), "labels": LabelNames(())}
            ),
            priority=Priority.medium,
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


# The status of each ticket in progress, repeated once per ticket.
class Occupancy(Value[tuple[IssueStatusName, ...]]):
    @staticmethod
    def fake() -> Occupancy:
        return Occupancy((IssueStatusName("Implementing"),))

    @staticmethod
    def of(issues: Issues) -> Occupancy:
        return Occupancy(tuple(issue.status for issue in issues.root))

    def plus(self, status: IssueStatusName) -> Occupancy:
        return Occupancy((*self.root, status))

    def under(self, status: IssueStatusName) -> Limit:
        return Limit(sum(1 for held in self.root if held.names(status).root))


class LimitSummary(Value[str]):
    @staticmethod
    def fake() -> LimitSummary:
        return LimitSummary("total 4, Grilling 1")


def default_status_limits() -> dict[IssueStatusName, Limit]:
    return {IssueStatusName("Grilling"): Limit(1)}


class PoolLimits(Model):
    total: Limit = Limit(4)
    statuses: dict[IssueStatusName, Limit] = Field(default_factory=default_status_limits)

    @staticmethod
    def fake() -> PoolLimits:
        return PoolLimits()

    # The table names statuses beside total, so each is read in the chart's spelling over the defaults.
    @model_validator(mode="before")
    @classmethod
    def statuses_beside_total(cls, data: JsonValue) -> JsonValue:
        if not isinstance(data, dict) or "statuses" in data:
            return data
        chart = StatusNames(
            tuple(IssueStatusName(state.root) for state in StateNames.of_chart(WorkflowChart).root)
        )
        statuses: dict[str, JsonValue] = {
            name.root: limit.root for name, limit in default_status_limits().items()
        }
        for key, limit in data.items():
            if key == "total":
                continue
            known = chart.matching(IssueStatusName(key))
            if known is None:
                listed = ", ".join(sorted(status.root for status in chart.root))
                raise ValueError(f"{key} is not a status in the chart. Limit one of {listed}.")
            statuses[known.root] = limit
        return {**{key: data[key] for key in ("total",) if key in data}, "statuses": statuses}

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
        return Admitted(limit is None or occupancy.under(status).root < limit.root)
