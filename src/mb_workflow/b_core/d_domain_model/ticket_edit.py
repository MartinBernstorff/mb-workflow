from mb_workflow.b_core.d_domain_model.issue import (
    Assignee,
    Cleared,
    IssueDescription,
    IssueDetail,
    IssueTitle,
    IssueUpdate,
    LabelNames,
    Milestone,
    MilestoneName,
    ProjectName,
)
from mb_workflow.d_lib.models import Model, Value


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
    milestone: MilestoneName | None
    remove_milestone: RemoveMilestone

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
            milestone=None,
            remove_milestone=RemoveMilestone(False),
        )

    def checked(self) -> TicketEdit:
        if self == TicketEdit.nothing():
            raise TicketEditError("Specify at least one field to edit.")
        if self.body is not None and self.body_file is not None:
            raise TicketEditError("Specify only one of --body and --body-file.")
        if self.milestone is not None and self.remove_milestone.root:
            raise TicketEditError("Specify only one of --milestone and --remove-milestone.")
        return self

    def update(self, current: IssueDetail, viewer: Assignee) -> IssueUpdate:
        project = self.checked()._project(current)
        return IssueUpdate(
            title=self.title,
            description=self.body if self.body is not None else self.body_file,
            labels=self._labels(current),
            assignee=self._assignee(current, viewer),
            project=project,
            milestone=self._milestone(current, project),
        )

    def _labels(self, current: IssueDetail) -> LabelNames | None:
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
