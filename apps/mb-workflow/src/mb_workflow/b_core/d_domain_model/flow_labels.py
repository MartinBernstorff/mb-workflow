from safe_result import Err, Ok, Result

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
    Matches,
)
from mb_workflow.d_lib.models import Model, Value


class FlowLabelOptionError(ValueError):
    pass


class LabelRename(Model):
    held: LabelName
    renamed: LabelName

    @staticmethod
    def fake() -> LabelRename:
        return LabelRename(held=LabelName("implementing"), renamed=LabelName("Implementing"))


class LabelRenames(Value[tuple[LabelRename, ...]]):
    @staticmethod
    def fake() -> LabelRenames:
        return LabelRenames((LabelRename.fake(),))


# The changes that bring one label group in line with the flow labels.
class GroupSync(Model):
    renamed: LabelRenames
    deleted: LabelNames
    recolored: LabelNames

    @staticmethod
    def fake() -> GroupSync:
        return GroupSync(
            renamed=LabelRenames.fake(), deleted=LabelNames.fake(), recolored=LabelNames(())
        )

    @staticmethod
    def unchanged() -> GroupSync:
        return GroupSync(renamed=LabelRenames(()), deleted=LabelNames(()), recolored=LabelNames(()))

    # Renaming or deleting a label touches every ticket that carries it.
    def destructive(self) -> Matches:
        return Matches(bool(self.renamed.root or self.deleted.root))


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
        return FlowLabels(group=group, labels=FlowLabels.chart_labels(chart), entry=entry)

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

    def synced(self, held: ColoredLabels) -> GroupSync:
        names = held.label_names().root
        return GroupSync(
            renamed=LabelRenames(
                tuple(
                    LabelRename(held=label, renamed=spelled)
                    for label in names
                    if (spelled := self.labels.matching(label)) is not None and spelled != label
                )
            ),
            deleted=LabelNames(
                tuple(label for label in names if self.labels.matching(label) is None)
            ),
            recolored=self.labels.spelled(self.miscolored(held)),
        )

    # A flow label set by hand would disagree with the status, so the state is moved with --state instead.
    def checked_label_options(
        self, requested: LabelNames
    ) -> Result[LabelNames, FlowLabelOptionError]:
        passed = self.labels.spelled(requested)
        if not passed.root:
            return Ok(requested)
        listed = ", ".join(label.root for label in passed.root)
        return Err(
            FlowLabelOptionError(
                f"{listed} is a flow label. Move the ticket with `mw ticket edit --state` instead."
            )
        )

    def relabelled(self, held: LabelNames, state: StateName) -> LabelNames:
        return LabelNames((*self.without_flow_labels(held).root, LabelName(state.root)))

    def without_flow_labels(self, held: LabelNames) -> LabelNames:
        return LabelNames(
            tuple(label for label in held.root if self.labels.matching(label) is None)
        )

    @staticmethod
    def chart_labels(chart: type[WorkflowChart]) -> LabelNames:
        return LabelNames(tuple(LabelName(state.name) for state in chart.states))

    def state_of(
        self, chart: type[WorkflowChart], held: GroupedLabels
    ) -> Result[StateName | None, FlowError]:
        found = held.in_group(self.group).root
        if not found:
            return Ok(None)
        if len(found) > 1:
            listed = ", ".join(label.root for label in found)
            return Err(
                FlowError(f"The ticket carries the flow labels {listed}, but may carry only one.")
            )
        known = FlowLabels.chart_labels(chart).matching(found[0])
        if known is None:
            return Err(FlowError(f"{found[0].root} is no state of the chart."))
        return Ok(StateName(known.root))
