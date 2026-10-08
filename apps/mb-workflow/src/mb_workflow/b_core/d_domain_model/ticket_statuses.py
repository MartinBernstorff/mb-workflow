from pydantic import field_validator
from safe_result import Err, Ok

from mb_workflow.b_core.d_domain_model.flow import AcceptedStates, StateName, WorkflowChart
from mb_workflow.b_core.d_domain_model.issue import IssueStatusName
from mb_workflow.d_lib.models import Value


class TicketStatuses(Value[dict[StateName, IssueStatusName]]):
    @staticmethod
    def fake() -> TicketStatuses:
        return TicketStatuses(
            {
                StateName(state): IssueStatusName(status)
                for state, status in (
                    ("grill", "Maturing"),
                    ("to-ticket", "Maturing"),
                    ("todo", "Todo"),
                    ("implementing", "In Progress"),
                    ("agent-reviewing", "In Progress"),
                    ("qa", "In Progress"),
                    ("review", "In Review"),
                    ("merging", "Ready For Release"),
                    ("merged", "Done"),
                )
            }
        )

    # A state is named ignoring case, and kept as the chart spells it.
    @field_validator("root")
    @classmethod
    def maps_exactly_the_chart_states(
        cls, mapped: dict[StateName, IssueStatusName]
    ) -> dict[StateName, IssueStatusName]:
        chart = AcceptedStates.of_chart(WorkflowChart)
        spelled: dict[StateName, IssueStatusName] = {}
        typed_as: dict[StateName, StateName] = {}
        unknown: list[str] = []
        for name, status in mapped.items():
            match chart.named_ignoring_case(name):
                case Ok(known):
                    if known in typed_as:
                        raise ValueError(
                            f"{typed_as[known].root}, {name.root} both map {known.root}."
                            " Keep one of them."
                        )
                    typed_as[known] = name
                    spelled[known] = status
                case Err():
                    unknown.append(name.root)
        if unknown:
            listed = ", ".join(state.root for state in chart.root)
            raise ValueError(
                f"The chart has no state named {', '.join(unknown)}. Map each of {listed}."
            )
        missing = [state.root for state in chart.root if state not in spelled]
        if missing:
            raise ValueError(f"[ticket_statuses] lacks {', '.join(missing)}.")
        return spelled

    def of(self, state: StateName) -> IssueStatusName:
        return self.root[state]
