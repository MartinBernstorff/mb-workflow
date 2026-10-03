from enum import IntEnum
from typing import TYPE_CHECKING

from pydantic import Field, JsonValue, NonNegativeInt, field_validator, model_validator

from mb_workflow.b_core.d_domain_model.flow import (
    AcceptedStates,
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

if TYPE_CHECKING:
    from safe_result import Result

    from mb_workflow.b_core.d_domain_model.flow import FlowError


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


class SkipsLimits(Value[bool]):
    @staticmethod
    def fake() -> SkipsLimits:
        return SkipsLimits(False)


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

    def flow_state(self, flow_labels: FlowLabels) -> Result[StateName | None, FlowError]:
        return state_of(WorkflowChart, flow_labels, self.issue.grouped)

    def slot(self, flow_labels: FlowLabels) -> Slot | None:
        return Slot.of(self.issue, flow_labels)

    def ready(self, claim_label: LabelName, flow_labels: FlowLabels) -> Ready:
        return Ready(
            self.flow_state(flow_labels).unwrap_or(None) in PoolTicket.ready_states().root
            and self.issue.labels.matching(claim_label) is None
        )

    def skips_limits(self, skip_limits_label: LabelName) -> SkipsLimits:
        return SkipsLimits(self.issue.labels.matching(skip_limits_label) is not None)


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


class Filled(Value[bool]):
    @staticmethod
    def fake() -> Filled:
        return Filled(False)


class TicketCount(Value[NonNegativeInt]):
    @staticmethod
    def fake() -> TicketCount:
        return TicketCount(1)


class Slot(Model):
    state: StateName
    labels: LabelNames

    @staticmethod
    def fake() -> Slot:
        return Slot(state=StateName("Implementing"), labels=LabelNames(()))

    @staticmethod
    def of(issue: Issue, flow_labels: FlowLabels) -> Slot | None:
        # A ticket whose flow labels name no single state fills no slot, like one without a flow label.
        state = state_of(WorkflowChart, flow_labels, issue.grouped).unwrap_or(None)
        return None if state is None else Slot(state=state, labels=issue.labels)


class Occupancy(Value[tuple[Slot, ...]]):
    @staticmethod
    def fake() -> Occupancy:
        return Occupancy((Slot.fake(),))

    @staticmethod
    def of(issues: Issues, flow_labels: FlowLabels) -> Occupancy:
        slots = (Slot.of(issue, flow_labels) for issue in issues.root)
        return Occupancy(tuple(slot for slot in slots if slot is not None))

    def with_slot(self, slot: Slot) -> Occupancy:
        return Occupancy((*self.root, slot))

    def count_in(self, state: StateName) -> TicketCount:
        return TicketCount(sum(1 for slot in self.root if slot.state == state))

    def count_labelled(self, label: LabelName) -> TicketCount:
        return TicketCount(sum(1 for slot in self.root if slot.labels.matching(label) is not None))


class Refusal(Value[str]):
    @staticmethod
    def fake() -> Refusal:
        return Refusal("Grilling is at its limit of 1")


class LimitSummary(Value[str]):
    @staticmethod
    def fake() -> LimitSummary:
        return LimitSummary("total 4, Grilling 1")


def default_state_limits() -> dict[StateName, Limit]:
    return {StateName("Grilling"): Limit(1)}


class PoolLimits(Model):
    total: Limit = Limit(4)
    states: dict[StateName, Limit] = Field(default_factory=default_state_limits)
    labels: dict[LabelName, Limit] = Field(default_factory=dict)

    @staticmethod
    def fake() -> PoolLimits:
        return PoolLimits()

    @model_validator(mode="before")
    @classmethod
    def refuse_stray_limits(cls, data: JsonValue) -> JsonValue:
        if not isinstance(data, dict):
            return data
        stray = [key for key in data if key not in cls.model_fields]
        if stray:
            raise ValueError(
                f"{', '.join(stray)} is no pool limit (allowed are {', '.join(cls.model_fields)}). State limits sit under"
                " [pool.limits.states], label limits under [pool.limits.labels]."
            )
        return data

    @field_validator("states")
    @classmethod
    def spell_as_the_chart(cls, states: dict[StateName, Limit]) -> dict[StateName, Limit]:
        chart = AcceptedStates.of_chart(WorkflowChart)
        spelled: dict[StateName, Limit] = {}
        typed_as: dict[StateName, StateName] = {}
        for name, limit in states.items():
            known = chart.named_ignoring_case(name).unwrap()
            if known in typed_as:
                raise ValueError(
                    f"{typed_as[known].root}, {name.root} both limit {known.root}. Keep one of them."
                )
            typed_as[known] = name
            spelled[known] = limit
        return {**default_state_limits(), **spelled}

    def limited_labels(self) -> LabelNames:
        return LabelNames(tuple(self.labels))

    def summary(self) -> LimitSummary:
        return LimitSummary(
            ", ".join(
                (
                    f"total {self.total.root}",
                    *(f"{name.root} {limit.root}" for name, limit in self.states.items()),
                    *(f"label {name.root} {limit.root}" for name, limit in self.labels.items()),
                )
            )
        )

    def filled(self, occupancy: Occupancy) -> Filled:
        return Filled(len(occupancy.root) >= self.total.root)

    def refusal(self, occupancy: Occupancy, slot: Slot) -> Refusal | None:
        if self.filled(occupancy).root:
            return Refusal(f"the pool is at its total of {self.total.root}")
        state_limit = self.states.get(slot.state)
        if state_limit is not None and occupancy.count_in(slot.state).root >= state_limit.root:
            return Refusal(f"{slot.state.root} is at its limit of {state_limit.root}")
        for label, limit in self.labels.items():
            if (
                slot.labels.matching(label) is not None
                and occupancy.count_labelled(label).root >= limit.root
            ):
                return Refusal(f"label {label.root} is at its limit of {limit.root}")
        return None
