from typing import TYPE_CHECKING

from mb_workflow.b_core.d_domain_model.issue import (
    Assignee,
    IssueDescription,
    IssueIdentifier,
    IssueTitle,
    LabelNames,
    Milestone,
    MilestoneName,
    NewIssue,
    ProjectName,
    TeamKey,
)
from mb_workflow.d_lib.models import Model

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.flow import StateName
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses


class TicketDraftError(ValueError):
    pass


class TicketDefaults(Model):
    team: TeamKey | None
    project: ProjectName | None

    @staticmethod
    def fake() -> TicketDefaults:
        return TicketDefaults(team=None, project=ProjectName.fake())


class TicketDraft(Model):
    title: IssueTitle
    body: IssueDescription | None
    body_file: IssueDescription | None
    labels: LabelNames
    assignee: Assignee | None
    project: ProjectName | None
    milestone: MilestoneName | None
    blocks: tuple[IssueIdentifier, ...]
    blocked_by: tuple[IssueIdentifier, ...]

    @staticmethod
    def fake() -> TicketDraft:
        return TicketDraft(
            title=IssueTitle.fake(),
            body=None,
            body_file=None,
            labels=LabelNames(()),
            assignee=None,
            project=None,
            milestone=None,
            blocks=(),
            blocked_by=(),
        )

    def related(self) -> tuple[IssueIdentifier, ...]:
        return (*self.blocks, *self.blocked_by)

    def new_issue(
        self,
        *,
        defaults: TicketDefaults,
        start: StateName,
        flow_labels: FlowLabels,
        statuses: TicketStatuses,
        viewer: Assignee,
    ) -> NewIssue:
        if self.body is not None and self.body_file is not None:
            raise TicketDraftError("Specify only one of --body and --body-file.")
        project = self.project if self.project is not None else defaults.project
        return NewIssue(
            team=defaults.team,
            title=self.title,
            description=self.body if self.body is not None else self.body_file,
            labels=flow_labels.relabelled(self.labels, start),
            assignee=self.assignee.resolved(viewer) if self.assignee is not None else None,
            project=project,
            status=statuses.of(start),
            milestone=self._milestone(project),
            blocks=self.blocks,
            blocked_by=self.blocked_by,
        )

    def _milestone(self, project: ProjectName | None) -> Milestone | None:
        if self.milestone is None:
            return None
        if project is None:
            raise TicketDraftError("A ticket without a project cannot take a milestone.")
        return Milestone(project=project, name=self.milestone)
