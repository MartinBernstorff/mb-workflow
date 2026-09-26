from typing import Self

from pydantic import model_validator

from mb_workflow.b_core.d_domain_model.flow import StateName, WorkflowChart
from mb_workflow.b_core.d_domain_model.issue import IssueStatusName
from mb_workflow.d_lib.models import Value


class TicketStatuses(Value[dict[StateName, IssueStatusName]]):
    @staticmethod
    def fake() -> TicketStatuses:
        return TicketStatuses(
            {
                StateName(state): IssueStatusName(status)
                for state, status in (
                    ("Grilling", "Maturing"),
                    ("Speccing", "Maturing"),
                    ("Specced", "Todo"),
                    ("Implementing", "In Progress"),
                    ("QA", "In Progress"),
                    ("Review", "In Review"),
                    ("Merging", "Ready For Release"),
                    ("Merged", "Done"),
                )
            }
        )

    @model_validator(mode="after")
    def maps_every_flow_state(self) -> Self:
        chart = tuple(StateName(state.name) for state in WorkflowChart.states)
        unknown = [state.root for state in self.root if state not in chart]
        if unknown:
            listed = ", ".join(state.root for state in chart)
            raise ValueError(
                f"{', '.join(unknown)} is not a state in the chart. Map each of {listed}."
            )
        missing = [state.root for state in chart if state not in self.root]
        if missing:
            raise ValueError(f"[ticket_statuses] lacks {', '.join(missing)}.")
        return self

    def of(self, state: StateName) -> IssueStatusName:
        return self.root[state]
