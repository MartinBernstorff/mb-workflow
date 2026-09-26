from enum import IntEnum

from pydantic import Field, JsonValue, NonNegativeInt, field_validator, model_validator

from mb_workflow.b_core.d_domain_model.flow import (
    Skill,
    StateName,
    StateNames,
    WorkflowChart,
    WorkState,
)
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels, state_of
from mb_workflow.b_core.d_domain_model.issue import (
    GroupedLabel,
    GroupedLabels,
    Issue,
    IssueIdentifier,
    Issues,
    LabelName,
    LabelNames,
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
                update={
                    "labels": LabelNames((GroupedLabel.fake().label,)),
                    "grouped": GroupedLabels((GroupedLabel.fake(),)),
                }
            ),
            priority=Priority.medium,
        )

    # A ticket is ready when its state names a skill an agent can run.
    @staticmethod
    def ready_states() -> StateNames:
        return StateNames(
            frozenset(
                StateName(state.name)
                for state in WorkflowChart.states
                if isinstance(state, WorkState) and isinstance(state.action, Skill)
            )
        )

    def flow_state(self, flow_labels: FlowLabels) -> StateName | None:
        return state_of(WorkflowChart, flow_labels, self.issue.grouped)

    def ready(self, claim_label: LabelName, flow_labels: FlowLabels) -> Ready:
        return Ready(
            self.flow_state(flow_labels) in PoolTicket.ready_states().root
            and self.issue.labels.matching(claim_label) is None
        )


class PoolTickets(Value[tuple[PoolTicket, ...]]):
    @staticmethod
    def fake() -> PoolTickets:
        return PoolTickets((PoolTicket.fake(),))

    def ready(self, claim_label: LabelName, flow_labels: FlowLabels) -> PoolTickets:
        return PoolTickets(
            tuple(ticket for ticket in self.root if ticket.ready(claim_label, flow_labels).root)
        )

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


class Occupancy(Value[tuple[StateName, ...]]):
    @staticmethod
    def fake() -> Occupancy:
        return Occupancy((StateName("Implementing"),))

    @staticmethod
    def of(issues: Issues, flow_labels: FlowLabels) -> Occupancy:
        states = (state_of(WorkflowChart, flow_labels, issue.grouped) for issue in issues.root)
        return Occupancy(tuple(state for state in states if state is not None))

    def with_ticket_in(self, state: StateName) -> Occupancy:
        return Occupancy((*self.root, state))

    def count_in(self, state: StateName) -> TicketCount:
        return TicketCount(sum(1 for held in self.root if held == state))


class LimitSummary(Value[str]):
    @staticmethod
    def fake() -> LimitSummary:
        return LimitSummary("total 4, Grilling 1")


def default_state_limits() -> dict[StateName, Limit]:
    return {StateName("Grilling"): Limit(1)}


def chart_state_named(name: StateName) -> StateName | None:
    wanted = name.root.casefold()
    return next(
        (
            state
            for state in StateNames.of_chart(WorkflowChart).root
            if state.root.casefold() == wanted
        ),
        None,
    )


class PoolLimits(Model):
    total: Limit = Limit(4)
    states: dict[StateName, Limit] = Field(default_factory=default_state_limits)

    @staticmethod
    def fake() -> PoolLimits:
        return PoolLimits()

    # [pool.limits] lists state limits flat beside total, and they only override the defaults.
    @model_validator(mode="before")
    @classmethod
    def gather_state_limits(cls, data: JsonValue) -> JsonValue:
        if not isinstance(data, dict) or "states" in data:
            return data
        states: dict[str, JsonValue] = {
            name.root: limit.root for name, limit in default_state_limits().items()
        }
        states.update({key: limit for key, limit in data.items() if key != "total"})
        return {**{key: data[key] for key in ("total",) if key in data}, "states": states}

    @field_validator("states")
    @classmethod
    def spell_as_the_chart(cls, states: dict[StateName, Limit]) -> dict[StateName, Limit]:
        spelled: dict[StateName, Limit] = {}
        for name, limit in states.items():
            known = chart_state_named(name)
            if known is None:
                listed = ", ".join(
                    sorted(state.root for state in StateNames.of_chart(WorkflowChart).root)
                )
                raise ValueError(f"{name.root} is not a state in the chart. Limit one of {listed}.")
            spelled[known] = limit
        return spelled

    def summary(self) -> LimitSummary:
        return LimitSummary(
            ", ".join(
                (
                    f"total {self.total.root}",
                    *(f"{name.root} {limit.root}" for name, limit in self.states.items()),
                )
            )
        )

    def filled(self, occupancy: Occupancy) -> Filled:
        return Filled(len(occupancy.root) >= self.total.root)

    def admits(self, occupancy: Occupancy, state: StateName) -> Admitted:
        if self.filled(occupancy).root:
            return Admitted(False)
        limit = self.states.get(state)
        return Admitted(limit is None or occupancy.count_in(state).root < limit.root)
