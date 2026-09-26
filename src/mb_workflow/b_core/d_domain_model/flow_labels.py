from mb_workflow.b_core.d_domain_model.flow import FlowError, StateName, WorkflowChart
from mb_workflow.b_core.d_domain_model.issue import (
    GroupedLabels,
    LabelGroupName,
    LabelName,
    LabelNames,
)
from mb_workflow.d_lib.models import Model


class FlowLabels(Model):
    group: LabelGroupName
    labels: LabelNames

    @staticmethod
    def fake() -> FlowLabels:
        return FlowLabels.of_chart(WorkflowChart, LabelGroupName.fake())

    @staticmethod
    def of_chart(chart: type[WorkflowChart], group: LabelGroupName) -> FlowLabels:
        return FlowLabels(group=group, labels=chart_labels(chart))

    def missing(self, held: LabelNames) -> LabelNames:
        return held.unmatched(self.labels)

    def relabelled(self, held: LabelNames, state: StateName) -> LabelNames:
        kept = tuple(label for label in held.root if self.labels.matching(label) is None)
        return LabelNames((*kept, LabelName(state.root)))


def chart_labels(chart: type[WorkflowChart]) -> LabelNames:
    return LabelNames(tuple(LabelName(state.name) for state in chart.states))


def state_of(
    chart: type[WorkflowChart], flow_labels: FlowLabels, held: GroupedLabels
) -> StateName | None:
    found = held.in_group(flow_labels.group).root
    if not found:
        return None
    if len(found) > 1:
        listed = ", ".join(label.root for label in found)
        raise FlowError(f"The ticket carries the flow labels {listed}, but may carry only one.")
    known = chart_labels(chart).matching(found[0])
    if known is None:
        raise FlowError(f"{found[0].root} is no state of the chart.")
    return StateName(known.root)
