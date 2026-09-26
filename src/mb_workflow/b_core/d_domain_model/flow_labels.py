from mb_workflow.b_core.d_domain_model.flow import WorkflowChart
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
        return FlowLabels(
            group=group, labels=LabelNames(tuple(LabelName(state.name) for state in chart.states))
        )

    def missing(self, held: LabelNames) -> LabelNames:
        return held.unmatched(self.labels)
