from contextlib import contextmanager
from typing import TYPE_CHECKING, override

from linear_python_client import (
    FindLabelRequest,
    FindUserRequest,
    IssueAddLabelRequest,
    IssueLabelsRequest,
    IssueUpdateRequest,
    LinearClient,
    LinearError,
)
from pydantic import AliasPath, Field

from mb_workflow.b_core.c_secondary_ports.issue_tracker import IssueTracker, IssueTrackerError
from mb_workflow.b_core.d_domain_model.issue import (
    Assigned,
    Assignee,
    Cleared,
    Issue,
    IssueDescription,
    IssueDetail,
    IssueIdentifier,
    Issues,
    IssueTitle,
    LabelName,
    LabelNames,
    Milestone,
    MilestoneName,
    ProjectName,
    StatusName,
)
from mb_workflow.d_lib.models import Payload, Value

if TYPE_CHECKING:
    from collections.abc import Generator

    from mb_workflow.b_core.d_domain_model.issue import IssueFilter, IssueUpdate


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
            raise IssueTrackerError(f"{self.name.root} has no milestone named {name.root}.")
        return found.id


class ProjectSearch(Payload):
    projects: tuple[ProjectRecord, ...] = Field(validation_alias=AliasPath("projects", "nodes"))

    @staticmethod
    def fake() -> ProjectSearch:
        return ProjectSearch(projects=(ProjectRecord.fake(),))

    def only(self, name: ProjectName) -> ProjectRecord:
        if not self.projects:
            raise IssueTrackerError(f"No project is named {name.root}.")
        return self.projects[0]


class IssuePayload(Payload):
    identifier: IssueIdentifier
    status: StatusName = Field(validation_alias=AliasPath("state", "name"))
    project: ProjectPayload | None = None
    labels: tuple[LabelPayload, ...] = Field(
        default=(), validation_alias=AliasPath("labels", "nodes")
    )
    assignee: AssigneePayload | None = None

    @staticmethod
    def fake() -> IssuePayload:
        return IssuePayload(
            identifier=IssueIdentifier.fake(),
            status=StatusName.fake(),
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


class IssueDetailPayload(IssuePayload):
    title: IssueTitle
    description: IssueDescription | None = None
    milestone: MilestonePayload | None = Field(default=None, validation_alias="projectMilestone")

    @override
    @staticmethod
    def fake() -> IssueDetailPayload:
        return IssueDetailPayload(
            identifier=IssueIdentifier.fake(),
            status=StatusName.fake(),
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


@contextmanager
def translated_errors() -> Generator[None]:
    try:
        yield
    except LinearError as error:
        raise IssueTrackerError(str(error)) from error


# The client's own issue queries leave out the project, which the sweep's exclusions read.
class Linear(IssueTracker):
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
    def set_labels(self, issue: IssueIdentifier, labels: LabelNames) -> None:
        label_ids = [self._label_id(label).root for label in labels.root]
        with translated_errors():
            _ = self._client.update_issue(IssueUpdateRequest(id=issue.root, label_ids=label_ids))

    @override
    def assign(self, issue: IssueIdentifier, assignee: Assignee) -> None:
        with translated_errors():
            user = self._client.find_user(FindUserRequest(email=assignee.root)).user
            if user is None or user.id is None:
                raise IssueTrackerError(f"No Linear user has the email {assignee.root}.")
            _ = self._client.update_issue(IssueUpdateRequest(id=issue.root, assignee_id=user.id))

    @override
    def update_issue(self, issue: IssueIdentifier, update: IssueUpdate) -> None:
        changes: dict[str, object] = {}
        if update.title is not None:
            changes["title"] = update.title
        if update.description is not None:
            changes["description"] = update.description
        if update.labels is not None:
            changes["label_ids"] = tuple(self._label_id(label) for label in update.labels.root)
        if update.assignee is not None:
            changes["assignee_id"] = self._user_id(update.assignee)
        if update.project is not None:
            changes["project_id"] = self._project_id(update.project)
        if update.milestone is not None:
            changes["project_milestone_id"] = self._milestone_id(update.milestone)
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
            raise IssueTrackerError("Linear did not say who the API key belongs to.")
        return Assignee(viewer.email)

    def _user_id(self, assignee: Assignee | Cleared) -> UserId | None:
        if isinstance(assignee, Cleared):
            return None
        with translated_errors():
            user = self._client.find_user(FindUserRequest(email=assignee.root)).user
        if user is None or user.id is None:
            raise IssueTrackerError(f"No Linear user has the email {assignee.root}.")
        return UserId(user.id)

    def _project_id(self, project: ProjectName | Cleared) -> ProjectId | None:
        if isinstance(project, Cleared):
            return None
        return self._project(project).id

    def _milestone_id(self, milestone: Milestone | Cleared) -> MilestoneId | None:
        if isinstance(milestone, Cleared):
            return None
        return self._project(milestone.project).milestone(milestone.name)

    def _project(self, name: ProjectName) -> ProjectRecord:
        with translated_errors():
            data = self._client.execute(
                """
                query($name: String!) {
                  projects(first: 1, filter: { name: { eqIgnoreCase: $name } }) {
                    nodes { id name projectMilestones { nodes { id name } } }
                  }
                }
                """,
                {"name": name.root},
            )
        return ProjectSearch.model_validate(data).only(name)

    def _label_id(self, label: LabelName) -> LabelId:
        with translated_errors():
            found = self._client.find_label(FindLabelRequest(name=label.root)).label
        if found is None or found.id is None:
            raise IssueTrackerError(f"No label is named {label.root}.")
        return LabelId(found.id)
