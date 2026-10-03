from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from mb_workflow.b_core.d_domain_model.flow import (
    AcceptedStates,
    StateName,
    UnknownStateError,
    WorkflowChart,
)
from mb_workflow.b_core.d_domain_model.issue import (
    Assignee,
    Cleared,
    IssueDescription,
    IssueDetail,
    IssueIdentifier,
    IssueTitle,
    IssueUpdate,
    LabelNames,
    Milestone,
    MilestoneName,
    ProjectName,
)
from mb_workflow.d_lib.models import Model, Value

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabelOptionError, FlowLabels
    from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses


class TicketEditError(ValueError):
    pass


class RemoveMilestone(Value[bool]):
    @staticmethod
    def fake() -> RemoveMilestone:
        return RemoveMilestone(False)


class TicketEdit(Model):
    title: IssueTitle | None
    body: IssueDescription | None
    body_file: IssueDescription | None
    add_labels: LabelNames
    remove_labels: LabelNames
    add_assignee: Assignee | None
    remove_assignee: Assignee | None
    add_project: ProjectName | None
    remove_project: ProjectName | None
    state: StateName | None
    milestone: MilestoneName | None
    remove_milestone: RemoveMilestone
    add_blocks: tuple[IssueIdentifier, ...]
    add_blocked_by: tuple[IssueIdentifier, ...]

    @staticmethod
    def fake() -> TicketEdit:
        return TicketEdit.nothing().model_copy(update={"title": IssueTitle.fake()})

    @staticmethod
    def nothing() -> TicketEdit:
        return TicketEdit(
            title=None,
            body=None,
            body_file=None,
            add_labels=LabelNames(()),
            remove_labels=LabelNames(()),
            add_assignee=None,
            remove_assignee=None,
            add_project=None,
            remove_project=None,
            state=None,
            milestone=None,
            remove_milestone=RemoveMilestone(False),
            add_blocks=(),
            add_blocked_by=(),
        )

    def checked(
        self, flow_labels: FlowLabels, issue: IssueIdentifier
    ) -> Result[TicketEdit, TicketEditError | FlowLabelOptionError | UnknownStateError]:
        if self == TicketEdit.nothing():
            return Err(TicketEditError("Specify at least one field to edit."))
        if self.body is not None and self.body_file is not None:
            return Err(TicketEditError("Specify only one of --body and --body-file."))
        if self.milestone is not None and self.remove_milestone.root:
            return Err(TicketEditError("Specify only one of --milestone and --remove-milestone."))
        if issue in self.related_issues():
            return Err(TicketEditError(f"{issue.root} cannot block or be blocked by itself."))
        match flow_labels.checked_label_options(
            LabelNames((*self.add_labels.root, *self.remove_labels.root))
        ):
            case Ok():
                return self._with_state_spelled_as_chart()
            case Err() as failed:
                return failed

    def _with_state_spelled_as_chart(self) -> Result[TicketEdit, UnknownStateError]:
        if self.state is None:
            return Ok(self)
        match AcceptedStates.of_chart(WorkflowChart).named_ignoring_case(self.state):
            case Ok(state):
                return Ok(self.model_copy(update={"state": state}))
            case Err() as failed:
                return failed

    # Expects an edit that passed checked.
    def update(
        self,
        current: IssueDetail,
        viewer: Assignee,
        flow_labels: FlowLabels,
        statuses: TicketStatuses,
    ) -> IssueUpdate:
        project = self._project(current)
        return IssueUpdate(
            title=self.title,
            description=self.body if self.body is not None else self.body_file,
            labels=self._labels(current, flow_labels),
            assignee=self._assignee(current, viewer),
            project=project,
            status=statuses.of(self.state) if self.state is not None else None,
            milestone=self._milestone(current, project),
            blocks=TicketEdit._unheld(self.add_blocks, current.blocks),
            blocked_by=TicketEdit._unheld(self.add_blocked_by, current.blocked_by),
        )

    @staticmethod
    def _unheld(
        added: tuple[IssueIdentifier, ...], held: frozenset[IssueIdentifier]
    ) -> tuple[IssueIdentifier, ...]:
        return tuple(issue for issue in dict.fromkeys(added) if issue not in held)

    def related_issues(self) -> tuple[IssueIdentifier, ...]:
        return (*self.add_blocks, *self.add_blocked_by)

    # The state is set without consulting the chart's moves, as the manual override of `mw flow`.
    def _labels(self, current: IssueDetail, flow_labels: FlowLabels) -> LabelNames | None:
        edited = self._edited_labels(current)
        if self.state is None:
            return edited
        held = current.issue.labels if edited is None else edited
        return flow_labels.relabelled(held, self.state)

    def _edited_labels(self, current: IssueDetail) -> LabelNames | None:
        if not self.add_labels.root and not self.remove_labels.root:
            return None
        kept = LabelNames(
            tuple(
                label
                for label in current.issue.labels.root
                if self.remove_labels.matching(label) is None
            )
        )
        return LabelNames((*kept.root, *kept.unmatched(self.add_labels).root))

    def _assignee(self, current: IssueDetail, viewer: Assignee) -> Assignee | Cleared | None:
        if self.add_assignee is not None:
            return self.add_assignee.resolved(viewer)
        if self.remove_assignee is not None and self.remove_assignee.resolved(viewer) == (
            current.assignee
        ):
            return Cleared()
        return None

    def _project(self, current: IssueDetail) -> ProjectName | Cleared | None:
        if self.add_project is not None:
            return self.add_project
        held = current.issue.project
        if self.remove_project is not None and held is not None:
            return Cleared() if self.remove_project.names(held).root else None
        return None

    def _milestone(
        self, current: IssueDetail, project: ProjectName | Cleared | None
    ) -> Milestone | Cleared | None:
        if self.remove_milestone.root:
            return Cleared()
        if self.milestone is None:
            return None
        target = current.issue.project if project is None else project
        if not isinstance(target, ProjectName):
            raise TicketEditError(
                f"{current.issue.identifier.root} has no project, so it cannot take a milestone."
            )
        return Milestone(project=target, name=self.milestone)
