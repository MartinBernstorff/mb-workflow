from contextlib import contextmanager
from typing import TYPE_CHECKING, override

from linear_python_client import (
    FindLabelRequest,
    FindUserRequest,
    IssueAddLabelRequest,
    IssueLabelsRequest,
    IssueRemoveLabelRequest,
    IssueUpdateRequest,
    LinearClient,
    LinearError,
)
from pydantic import AliasPath, Field

from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker, TicketTrackerError
from mb_workflow.b_core.d_domain_model.issue import (
    Assigned,
    Assignee,
    Cleared,
    Issue,
    IssueDescription,
    IssueDetail,
    IssueIdentifier,
    Issues,
    IssueStatusName,
    IssueTitle,
    LabelName,
    LabelNames,
    Milestone,
    MilestoneName,
    ProjectName,
)
from mb_workflow.b_core.d_domain_model.pool import (
    Blocker,
    Blockers,
    PoolTicket,
    PoolTickets,
    Priority,
)
from mb_workflow.d_lib.models import Payload, Value

if TYPE_CHECKING:
    from collections.abc import Generator

    from mb_workflow.b_core.d_domain_model.issue import IssueFilter, IssueUpdate
    from mb_workflow.b_core.d_domain_model.pool import ViewSlug


class LinearApiKey(Value[str]):
    @staticmethod
    def fake() -> LinearApiKey:
        return LinearApiKey("lin_api_0000000000000000000000000000000000000000")


class LabelId(Value[str]):
    @staticmethod
    def fake() -> LabelId:
        return LabelId("8eeefaa9-c4f3-4ca4-af53-4b2aa2078d1e")


class PageCursor(Value[str]):
    @staticmethod
    def fake() -> PageCursor:
        return PageCursor("17bec4c8-ce66-4546-a54f-aaefbc27e32f")


class MorePages(Value[bool]):
    @staticmethod
    def fake() -> MorePages:
        return MorePages(True)


class PageInfo(Payload):
    has_next_page: MorePages
    end_cursor: PageCursor | None = None

    @staticmethod
    def fake() -> PageInfo:
        return PageInfo(has_next_page=MorePages.fake(), end_cursor=PageCursor.fake())

    def next_cursor(self) -> PageCursor | None:
        return self.end_cursor if self.has_next_page.root else None


class LabelPayload(Payload):
    name: LabelName

    @staticmethod
    def fake() -> LabelPayload:
        return LabelPayload(name=LabelName.fake())


class ProjectPayload(Payload):
    name: ProjectName

    @staticmethod
    def fake() -> ProjectPayload:
        return ProjectPayload(name=ProjectName.fake())


# The sweep only asks whether someone is assigned, so it leaves the email out.
class AssigneePayload(Payload):
    email: Assignee | None = None

    @staticmethod
    def fake() -> AssigneePayload:
        return AssigneePayload(email=Assignee.fake())


class MilestonePayload(Payload):
    name: MilestoneName

    @staticmethod
    def fake() -> MilestonePayload:
        return MilestonePayload(name=MilestoneName.fake())


class UserId(Value[str]):
    @staticmethod
    def fake() -> UserId:
        return UserId("0b8e6c1f-7d2a-4f5e-9c3b-1a2d4e6f8a0c")


class ProjectId(Value[str]):
    @staticmethod
    def fake() -> ProjectId:
        return ProjectId("3d9f1e2a-5b7c-4a8d-8e6f-0c1b2a3d4e5f")


class MilestoneId(Value[str]):
    @staticmethod
    def fake() -> MilestoneId:
        return MilestoneId("9a1c3e5b-2d4f-4b6a-8c0e-7f1a3b5c7d9e")


class StateId(Value[str]):
    @staticmethod
    def fake() -> StateId:
        return StateId("5c7e9a1b-3d5f-4e7a-9b1c-2d4e6f8a0b2c")


class StateRecord(Payload):
    id: StateId
    name: IssueStatusName

    @staticmethod
    def fake() -> StateRecord:
        return StateRecord(id=StateId.fake(), name=IssueStatusName.fake())


class LabelRecord(Payload):
    id: LabelId
    name: LabelName

    @staticmethod
    def fake() -> LabelRecord:
        return LabelRecord(id=LabelId.fake(), name=LabelName.fake())


class UserRecord(Payload):
    id: UserId

    @staticmethod
    def fake() -> UserRecord:
        return UserRecord(id=UserId.fake())


class MilestoneRecord(Payload):
    id: MilestoneId
    name: MilestoneName

    @staticmethod
    def fake() -> MilestoneRecord:
        return MilestoneRecord(id=MilestoneId.fake(), name=MilestoneName.fake())


class ProjectRecord(Payload):
    id: ProjectId
    name: ProjectName
    milestones: tuple[MilestoneRecord, ...] = Field(
        default=(), validation_alias=AliasPath("projectMilestones", "nodes")
    )

    @staticmethod
    def fake() -> ProjectRecord:
        return ProjectRecord(
            id=ProjectId.fake(), name=ProjectName.fake(), milestones=(MilestoneRecord.fake(),)
        )

    def milestone(self, name: MilestoneName) -> MilestoneId:
        found = next((known for known in self.milestones if known.name.names(name).root), None)
        if found is None:
            raise TicketTrackerError(f"{self.name.root} has no milestone named {name.root}.")
        return found.id


# One read resolves every name an update carries, each part included only when the update needs it.
class UpdateLookup(Payload):
    labels: tuple[LabelRecord, ...] = Field(
        default=(), validation_alias=AliasPath("issueLabels", "nodes")
    )
    users: tuple[UserRecord, ...] = Field(default=(), validation_alias=AliasPath("users", "nodes"))
    projects: tuple[ProjectRecord, ...] = Field(
        default=(), validation_alias=AliasPath("project", "nodes")
    )
    milestone_projects: tuple[ProjectRecord, ...] = Field(
        default=(), validation_alias=AliasPath("milestoneProject", "nodes")
    )
    states: tuple[StateRecord, ...] = Field(
        default=(), validation_alias=AliasPath("issue", "team", "states", "nodes")
    )

    @staticmethod
    def fake() -> UpdateLookup:
        return UpdateLookup(
            labels=(LabelRecord.fake(),),
            users=(UserRecord.fake(),),
            projects=(ProjectRecord.fake(),),
            milestone_projects=(ProjectRecord.fake(),),
            states=(StateRecord.fake(),),
        )

    def label_ids(self, labels: LabelNames) -> tuple[LabelId, ...]:
        known = LabelNames(tuple(record.name for record in self.labels))
        unknown = known.unmatched(labels)
        if unknown.root:
            raise TicketTrackerError(
                f"No label is named {', '.join(label.root for label in unknown.root)}."
            )
        return tuple(
            next(record.id for record in self.labels if record.name == name)
            for name in known.spelled(labels).root
        )

    def user_id(self, assignee: Assignee | Cleared) -> UserId | None:
        if isinstance(assignee, Cleared):
            return None
        if not self.users:
            raise TicketTrackerError(f"No Linear user has the email {assignee.root}.")
        return self.users[0].id

    def project_id(self, project: ProjectName | Cleared) -> ProjectId | None:
        if isinstance(project, Cleared):
            return None
        if not self.projects:
            raise TicketTrackerError(f"No project is named {project.root}.")
        return self.projects[0].id

    def milestone_id(self, milestone: Milestone | Cleared) -> MilestoneId | None:
        if isinstance(milestone, Cleared):
            return None
        if not self.milestone_projects:
            raise TicketTrackerError(f"No project is named {milestone.project.root}.")
        return self.milestone_projects[0].milestone(milestone.name)

    def state_id(self, status: IssueStatusName) -> StateId:
        found = next((known for known in self.states if known.name.names(status).root), None)
        if found is None:
            raise TicketTrackerError(f"No status is named {status.root}.")
        return found.id


class IssuePayload(Payload):
    identifier: IssueIdentifier
    status: IssueStatusName = Field(validation_alias=AliasPath("state", "name"))
    project: ProjectPayload | None = None
    labels: tuple[LabelPayload, ...] = Field(
        default=(), validation_alias=AliasPath("labels", "nodes")
    )
    assignee: AssigneePayload | None = None

    @staticmethod
    def fake() -> IssuePayload:
        return IssuePayload(
            identifier=IssueIdentifier.fake(),
            status=IssueStatusName.fake(),
            project=ProjectPayload.fake(),
            labels=(LabelPayload.fake(),),
        )

    def issue(self) -> Issue:
        return Issue(
            identifier=self.identifier,
            status=self.status,
            project=self.project.name if self.project is not None else None,
            labels=LabelNames(tuple(label.name for label in self.labels)),
            assigned=Assigned(self.assignee is not None),
        )


class RelationType(Value[str]):
    @staticmethod
    def fake() -> RelationType:
        return RelationType.blocks()

    @staticmethod
    def blocks() -> RelationType:
        return RelationType("blocks")


class RelatedIssuePayload(Payload):
    identifier: IssueIdentifier
    status: IssueStatusName = Field(validation_alias=AliasPath("state", "name"))

    @staticmethod
    def fake() -> RelatedIssuePayload:
        return RelatedIssuePayload(identifier=IssueIdentifier.fake(), status=IssueStatusName.fake())


# Linear stores only "A blocks B", so a ticket's blockers are its inverse relations of that type.
class InverseRelationPayload(Payload):
    type: RelationType
    issue: RelatedIssuePayload

    @staticmethod
    def fake() -> InverseRelationPayload:
        return InverseRelationPayload(type=RelationType.fake(), issue=RelatedIssuePayload.fake())


class PoolTicketPayload(IssuePayload):
    priority: Priority
    inverse_relations: tuple[InverseRelationPayload, ...] = Field(
        default=(), validation_alias=AliasPath("inverseRelations", "nodes")
    )
    more_relations: MorePages = Field(
        default=MorePages(False),
        validation_alias=AliasPath("inverseRelations", "pageInfo", "hasNextPage"),
    )

    @override
    @staticmethod
    def fake() -> PoolTicketPayload:
        return PoolTicketPayload(
            identifier=IssueIdentifier.fake(),
            status=IssueStatusName.fake(),
            project=ProjectPayload.fake(),
            labels=(LabelPayload.fake(),),
            priority=Priority.medium,
            inverse_relations=(InverseRelationPayload.fake(),),
        )

    # A blocker left off the read would pass the ticket as ready, so a partial read is refused.
    def ticket(self) -> PoolTicket:
        if self.more_relations.root:
            raise TicketTrackerError(
                f"{self.identifier.root} has more relations than one read of the view lists."
            )
        return PoolTicket(
            issue=self.issue(),
            priority=self.priority,
            blockers=Blockers(
                tuple(
                    Blocker(issue=relation.issue.identifier, status=relation.issue.status)
                    for relation in self.inverse_relations
                    if relation.type == RelationType.blocks()
                )
            ),
        )


class IssueDetailPayload(IssuePayload):
    title: IssueTitle
    description: IssueDescription | None = None
    milestone: MilestonePayload | None = Field(default=None, validation_alias="projectMilestone")

    @override
    @staticmethod
    def fake() -> IssueDetailPayload:
        return IssueDetailPayload(
            identifier=IssueIdentifier.fake(),
            status=IssueStatusName.fake(),
            project=ProjectPayload.fake(),
            labels=(LabelPayload.fake(),),
            title=IssueTitle.fake(),
            description=IssueDescription.fake(),
        )

    def detail(self) -> IssueDetail:
        return IssueDetail(
            issue=self.issue(),
            title=self.title,
            description=self.description,
            assignee=self.assignee.email if self.assignee is not None else None,
            milestone=self.milestone.name if self.milestone is not None else None,
        )


# A field left unset stays as it is, while one set to None is emptied.
class IssueChanges(Payload):
    title: IssueTitle | None = None
    description: IssueDescription | None = None
    label_ids: tuple[LabelId, ...] | None = None
    assignee_id: UserId | None = None
    project_id: ProjectId | None = None
    state_id: StateId | None = None
    project_milestone_id: MilestoneId | None = None

    @staticmethod
    def fake() -> IssueChanges:
        return IssueChanges(title=IssueTitle.fake())


class IssueDetailRead(Payload):
    issue: IssueDetailPayload

    @staticmethod
    def fake() -> IssueDetailRead:
        return IssueDetailRead(issue=IssueDetailPayload.fake())


class IssuePage(Payload):
    nodes: tuple[IssuePayload, ...]
    page_info: PageInfo

    @staticmethod
    def fake() -> IssuePage:
        return IssuePage(nodes=(IssuePayload.fake(),), page_info=PageInfo.fake())

    def issues(self) -> Issues:
        return Issues(tuple(node.issue() for node in self.nodes))


class IssueSweep(Payload):
    issues: IssuePage

    @staticmethod
    def fake() -> IssueSweep:
        return IssueSweep(issues=IssuePage.fake())


class PoolTicketPage(Payload):
    nodes: tuple[PoolTicketPayload, ...]
    page_info: PageInfo

    @staticmethod
    def fake() -> PoolTicketPage:
        return PoolTicketPage(nodes=(PoolTicketPayload.fake(),), page_info=PageInfo.fake())


class ViewRead(Payload):
    issues: PoolTicketPage = Field(validation_alias=AliasPath("customView", "issues"))

    @staticmethod
    def fake() -> ViewRead:
        return ViewRead(issues=PoolTicketPage.fake())


@contextmanager
def translated_errors() -> Generator[None]:
    try:
        yield
    except LinearError as error:
        raise TicketTrackerError(str(error)) from error


# The client's own issue queries leave out the project, which the sweep's exclusions read.
class Linear(TicketTracker):
    def __init__(self, client: LinearClient) -> None:
        self._client = client

    @staticmethod
    def connected(key: LinearApiKey) -> Linear:
        return Linear(LinearClient(api_key=key.root))

    @override
    def workspace_labels(self) -> LabelNames:
        with translated_errors():
            labels = self._client.paginate(self._client.issue_labels, IssueLabelsRequest(first=250))
            return LabelNames(tuple(LabelName(label.name) for label in labels if label.name))

    @override
    def list_issues(self, wanted: IssueFilter) -> Issues:
        found: list[Issue] = []
        cursor: PageCursor | None = None
        while True:
            with translated_errors():
                data = self._client.execute(
                    """
                    query($filter: IssueFilter, $after: String) {
                      issues(first: 250, after: $after, filter: $filter) {
                        nodes {
                          identifier
                          state { name }
                          project { name }
                          labels { nodes { name } }
                          assignee { id }
                        }
                        pageInfo { hasNextPage endCursor }
                      }
                    }
                    """,
                    {
                        "filter": {
                            "creator": {"email": {"eq": wanted.creator.root}},
                            "createdAt": {"gte": wanted.created_after.root.isoformat()},
                        },
                        "after": cursor.root if cursor is not None else None,
                    },
                )
            page = IssueSweep.model_validate(data).issues
            found.extend(page.issues().root)
            cursor = page.page_info.next_cursor()
            if cursor is None:
                return Issues(tuple(found))

    # Linear caps a query's complexity at 10,000; relations nested under 250 issues exceed it.
    @override
    def view_tickets(self, view: ViewSlug) -> PoolTickets:
        found: list[PoolTicket] = []
        cursor: PageCursor | None = None
        while True:
            with translated_errors():
                data = self._client.execute(
                    """
                    query($view: String!, $after: String) {
                      customView(id: $view) {
                        issues(first: 40, after: $after) {
                          nodes {
                            identifier
                            priority
                            state { name }
                            project { name }
                            labels { nodes { name } }
                            assignee { id }
                            inverseRelations(first: 50) {
                              nodes { type issue { identifier state { name } } }
                              pageInfo { hasNextPage }
                            }
                          }
                          pageInfo { hasNextPage endCursor }
                        }
                      }
                    }
                    """,
                    {"view": view.root, "after": cursor.root if cursor is not None else None},
                )
            page = ViewRead.model_validate(data).issues
            found.extend(node.ticket() for node in page.nodes)
            cursor = page.page_info.next_cursor()
            if cursor is None:
                return PoolTickets(tuple(found))

    @override
    def read_issue(self, issue: IssueIdentifier) -> Issue:
        return self.read_issue_detail(issue).issue

    @override
    def read_issue_detail(self, issue: IssueIdentifier) -> IssueDetail:
        with translated_errors():
            data = self._client.execute(
                """
                query($id: String!) {
                  issue(id: $id) {
                    identifier
                    title
                    description
                    state { name }
                    project { name }
                    labels { nodes { name } }
                    assignee { email }
                    projectMilestone { name }
                  }
                }
                """,
                {"id": issue.root},
            )
        return IssueDetailRead.model_validate(data).issue.detail()

    @override
    def add_label(self, issue: IssueIdentifier, label: LabelName) -> None:
        label_id = self._label_id(label)
        with translated_errors():
            _ = self._client.add_label(IssueAddLabelRequest(id=issue.root, label_id=label_id.root))

    @override
    def remove_label(self, issue: IssueIdentifier, label: LabelName) -> None:
        label_id = self._label_id(label)
        with translated_errors():
            _ = self._client.remove_label(
                IssueRemoveLabelRequest(id=issue.root, label_id=label_id.root)
            )

    @override
    def set_labels(self, issue: IssueIdentifier, labels: LabelNames) -> None:
        label_ids = [self._label_id(label).root for label in labels.root]
        with translated_errors():
            _ = self._client.update_issue(IssueUpdateRequest(id=issue.root, label_ids=label_ids))

    @override
    def assign(self, issue: IssueIdentifier, assignee: Assignee) -> None:
        with translated_errors():
            user = self._client.find_user(FindUserRequest(email=assignee.root)).user
            if user is None or user.id is None:
                raise TicketTrackerError(f"No Linear user has the email {assignee.root}.")
            _ = self._client.update_issue(IssueUpdateRequest(id=issue.root, assignee_id=user.id))

    @override
    def update_issue(self, issue: IssueIdentifier, update: IssueUpdate) -> None:
        found = self._lookup(issue, update)
        changes: dict[str, object] = {}
        if update.title is not None:
            changes["title"] = update.title
        if update.description is not None:
            changes["description"] = update.description
        if update.labels is not None:
            changes["label_ids"] = found.label_ids(update.labels)
        if update.assignee is not None:
            changes["assignee_id"] = found.user_id(update.assignee)
        if update.project is not None:
            changes["project_id"] = found.project_id(update.project)
        if update.status is not None:
            changes["state_id"] = found.state_id(update.status)
        if update.milestone is not None:
            changes["project_milestone_id"] = found.milestone_id(update.milestone)
        wanted = IssueChanges.model_validate(changes)
        with translated_errors():
            _ = self._client.execute(
                "mutation($id: String!, $input: IssueUpdateInput!) {"
                " issueUpdate(id: $id, input: $input) { success } }",
                {
                    "id": issue.root,
                    "input": wanted.model_dump(mode="json", by_alias=True, exclude_unset=True),
                },
            )

    @override
    def viewer(self) -> Assignee:
        with translated_errors():
            viewer = self._client.viewer().viewer
        if viewer is None or viewer.email is None:
            raise TicketTrackerError("Linear did not say who the API key belongs to.")
        return Assignee(viewer.email)

    def _lookup(self, issue: IssueIdentifier, update: IssueUpdate) -> UpdateLookup:
        labels = update.labels.root if update.labels is not None else ()
        assignee = update.assignee if isinstance(update.assignee, Assignee) else None
        project = update.project if isinstance(update.project, ProjectName) else None
        milestone = update.milestone if isinstance(update.milestone, Milestone) else None
        if not (labels or assignee or project or milestone or update.status):
            return UpdateLookup()
        with translated_errors():
            data = self._client.execute(
                """
                query(
                  $issue: String!
                  $labels: IssueLabelFilter, $withLabels: Boolean!
                  $user: UserFilter, $withUser: Boolean!
                  $project: ProjectFilter, $withProject: Boolean!
                  $milestoneProject: ProjectFilter, $withMilestone: Boolean!
                  $withStates: Boolean!
                ) {
                  issueLabels(first: 250, filter: $labels) @include(if: $withLabels) {
                    nodes { id name }
                  }
                  users(first: 1, filter: $user) @include(if: $withUser) { nodes { id } }
                  project: projects(first: 1, filter: $project) @include(if: $withProject) {
                    nodes { id name }
                  }
                  milestoneProject: projects(first: 1, filter: $milestoneProject)
                    @include(if: $withMilestone) {
                    nodes { id name projectMilestones { nodes { id name } } }
                  }
                  issue(id: $issue) @include(if: $withStates) {
                    team { states(first: 250) { nodes { id name } } }
                  }
                }
                """,
                {
                    "issue": issue.root,
                    "labels": {"or": [{"name": {"eqIgnoreCase": label.root}} for label in labels]},
                    "withLabels": bool(labels),
                    "user": {"email": {"eq": assignee.root}} if assignee else None,
                    "withUser": assignee is not None,
                    "project": {"name": {"eqIgnoreCase": project.root}} if project else None,
                    "withProject": project is not None,
                    "milestoneProject": (
                        {"name": {"eqIgnoreCase": milestone.project.root}} if milestone else None
                    ),
                    "withMilestone": milestone is not None,
                    "withStates": update.status is not None,
                },
            )
        return UpdateLookup.model_validate(data)

    def _label_id(self, label: LabelName) -> LabelId:
        with translated_errors():
            found = self._client.find_label(FindLabelRequest(name=label.root)).label
        if found is None or found.id is None:
            raise TicketTrackerError(f"No label is named {label.root}.")
        return LabelId(found.id)
