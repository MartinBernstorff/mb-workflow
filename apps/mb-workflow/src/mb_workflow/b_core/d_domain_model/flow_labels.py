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
)
from mb_workflow.d_lib.models import Model, Value


class FlowLabelOptionError(ValueError):
    pass


class LabelRename(Model):
    held: LabelName
    renamed: LabelName

    @staticmethod
    def fake() -> LabelRename:
        return LabelRename(held=LabelName("Implementing"), renamed=LabelName("implementing"))


class LabelRenames(Value[tuple[LabelRename, ...]]):
    @staticmethod
    def fake() -> LabelRenames:
        return LabelRenames((LabelRename.fake(),))

    @staticmethod
    def former_state_labels() -> LabelRenames:
        return LabelRenames(
            tuple(
                LabelRename(held=LabelName(held), renamed=LabelName(renamed))
                for held, renamed in (
                    ("Grilling", "grill"),
                    ("Speccing", "to-ticket"),
                    ("Specced", "todo"),
                )
            )
        )

    def renamed_from(self, label: LabelName) -> LabelName | None:
        wanted = label.root.casefold()
        return next(
            (rename.renamed for rename in self.root if rename.held.root.casefold() == wanted),
            None,
        )


class GroupSync(Model):
    renamed: LabelRenames
    deleted: LabelNames
    recolored: LabelNames

    @staticmethod
    def fake() -> GroupSync:
        return GroupSync(
            renamed=LabelRenames.fake(), deleted=LabelNames.fake(), recolored=LabelNames.fake()
        )

    @staticmethod
    def unchanged() -> GroupSync:
        return GroupSync(renamed=LabelRenames(()), deleted=LabelNames(()), recolored=LabelNames(()))


class FlowLabels(Model):
    group: LabelGroupName
    labels: LabelNames
    entry: LabelNames
    former: LabelRenames

    @staticmethod
    def fake() -> FlowLabels:
        return FlowLabels.of_chart(
            WorkflowChart, LabelGroupName.fake(), LabelRenames.former_state_labels()
        )

    @staticmethod
    def of_chart(
        chart: type[WorkflowChart], group: LabelGroupName, former: LabelRenames
    ) -> FlowLabels:
        entry = LabelNames(
            tuple(
                LabelName(state.name)
                for state in chart.states
                if isinstance(state, WorkState) and state.phase == Phase.entry
            )
        )
        return FlowLabels(
            group=group, labels=FlowLabels.chart_labels(chart), entry=entry, former=former
        )

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

    def _color_of(self, label: LabelName) -> LabelColor:
        return LabelColor.yellow() if self.entry.matching(label) is not None else LabelColor.grey()

    def missing(self, held: LabelNames) -> LabelNames:
        return LabelNames(
            (*held.root, *(rename.renamed for rename in self._renames(held).root))
        ).unmatched(self.labels)

    def sync_plan(self, held: ColoredLabels) -> GroupSync:
        names = held.label_names()
        renamed = self._renames(names)
        return GroupSync(
            renamed=renamed,
            deleted=LabelNames(
                tuple(
                    label
                    for label in names.root
                    if self.labels.matching(label) is None
                    and all(rename.held != label for rename in renamed.root)
                )
            ),
            recolored=self.labels.spelled(self.miscolored(held)),
        )

    def _renames(self, held: LabelNames) -> LabelRenames:
        renames: list[LabelRename] = []
        for label in held.root:
            spelled = self.labels.matching(label)
            if spelled is not None:
                if spelled != label:
                    renames.append(LabelRename(held=label, renamed=spelled))
                continue
            current = self.former.renamed_from(label)
            if current is not None and held.matching(current) is None:
                renames.append(LabelRename(held=label, renamed=current))
        return LabelRenames(tuple(renames))

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
