from mb_workflow.b_core.d_domain_model.flow import (
    FlowError,
    Phase,
    StateName,
    WorkflowChart,
    WorkState,
)
from mb_workflow.b_core.d_domain_model.issue import (
    ColoredLabel,
    ColoredLabels,
    GroupedLabels,
    LabelColor,
    LabelGroupName,
    LabelName,
    LabelNames,
)
from mb_workflow.d_lib.models import Model


class FlowLabels(Model):
    group: LabelGroupName
    labels: LabelNames
    entry: LabelNames

    @staticmethod
    def fake() -> FlowLabels:
        return FlowLabels.of_chart(WorkflowChart, LabelGroupName.fake())

    @staticmethod
    def of_chart(chart: type[WorkflowChart], group: LabelGroupName) -> FlowLabels:
        entry = LabelNames(
            tuple(
                LabelName(state.name)
                for state in chart.states
                if isinstance(state, WorkState) and state.phase == Phase.entry
            )
        )
        return FlowLabels(group=group, labels=chart_labels(chart), entry=entry)

    def colored(self, labels: LabelNames) -> ColoredLabels:
        return ColoredLabels(
            tuple(ColoredLabel(name=label, color=self._color_of(label)) for label in labels.root)
        )

    def miscolored(self, held: ColoredLabels) -> LabelNames:
        return LabelNames(
            tuple(
                label.name
                for label in held.root
                if self.labels.matching(label.name) is not None
                and not self._color_of(label.name).matches(label.color).root
            )
        )

    # Entry labels stand out in yellow, so a ticket not yet ready for work is told apart at a glance.
    def _color_of(self, label: LabelName) -> LabelColor:
        return LabelColor.yellow() if self.entry.matching(label) is not None else LabelColor.grey()

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
