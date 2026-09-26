from mb_workflow.b_core.d_domain_model.flow import StateName, StateNames, WorkflowChart
from mb_workflow.b_core.d_domain_model.issue import LabelName, LabelNames
from mb_workflow.d_lib.models import Model, Value


class LabelGroupName(Value[str]):
    @staticmethod
    def fake() -> LabelGroupName:
        return LabelGroupName("flow")


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


def state_of(chart: type[WorkflowChart], held: LabelNames) -> StateName:
    found = next(iter(chart_labels(chart).spelled(held).root), None)
    return StateNames.initial_state(chart) if found is None else StateName(found.root)
