import os
from contextlib import contextmanager
from typing import TYPE_CHECKING, override

from linear_python_client import (
    FindLabelRequest,
    FindProjectRequest,
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
    Assignee,
    Clear,
    Issue,
    IssueBody,
    IssueIdentifier,
    Issues,
    IssueTitle,
    IssueUrl,
    LabelName,
    LabelNames,
    MilestoneName,
    ProjectName,
    StatusName,
)
from mb_workflow.d_lib.models import Payload, Value

if TYPE_CHECKING:
    from collections.abc import Generator

    from mb_workflow.b_core.d_domain_model.issue import IssueEdit, IssueFilter


class LinearApiKey(Value[str]):
    @staticmethod
    def fake() -> LinearApiKey:
        return LinearApiKey("lin_api_0000000000000000000000000000000000000000")

    @staticmethod
    def from_environment() -> LinearApiKey:
        key = os.environ.get("LINEAR_API_KEY")
        if not key:
            raise IssueTrackerError("Set LINEAR_API_KEY to a Linear personal API key.")
        return LinearApiKey(key)


class LabelId(Value[str]):
    @staticmethod
    def fake() -> LabelId:
        return LabelId("8eeefaa9-c4f3-4ca4-af53-4b2aa2078d1e")


class UserId(Value[str]):
    @staticmethod
    def fake() -> UserId:
        return UserId("2b0c1f4e-7d3a-4e8b-9c6f-5a1d2e3f4b5c")


class ProjectId(Value[str]):
    @staticmethod
    def fake() -> ProjectId:
        return ProjectId("9d4e2a1b-3c5f-4a6e-8b7d-1e2f3a4b5c6d")


class MilestoneId(Value[str]):
    @staticmethod
    def fake() -> MilestoneId:
        return MilestoneId("4f5e6d7c-8b9a-4c1d-9e2f-3a4b5c6d7e8f")


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


class MilestonePayload(Payload):
    name: MilestoneName

    @staticmethod
    def fake() -> MilestonePayload:
        return MilestonePayload(name=MilestoneName.fake())


class AssigneePayload(Payload):
    email: Assignee

    @staticmethod
    def fake() -> AssigneePayload:
        return AssigneePayload(email=Assignee.fake())


class IssuePayload(Payload):
    identifier: IssueIdentifier
    title: IssueTitle
    # Linear sends null for an issue that was never given a description.
    description: IssueBody | None = None
    status: StatusName = Field(validation_alias=AliasPath("state", "name"))
    project: ProjectPayload | None = None
    project_milestone: MilestonePayload | None = None
    labels: tuple[LabelPayload, ...] = Field(
        default=(), validation_alias=AliasPath("labels", "nodes")
    )
    assignee: AssigneePayload | None = None

    @staticmethod
    def fake() -> IssuePayload:
        return IssuePayload(
            identifier=IssueIdentifier.fake(),
            title=IssueTitle.fake(),
            description=IssueBody.fake(),
            status=StatusName.fake(),
            project=ProjectPayload.fake(),
            labels=(LabelPayload.fake(),),
        )

    def issue(self) -> Issue:
        return Issue(
            identifier=self.identifier,
            title=self.title,
            body=self.description if self.description is not None else IssueBody(""),
            status=self.status,
            project=self.project.name if self.project is not None else None,
            milestone=self.project_milestone.name if self.project_milestone is not None else None,
            labels=LabelNames(tuple(label.name for label in self.labels)),
            assignee=self.assignee.email if self.assignee is not None else None,
        )


class IssueRead(Payload):
    issue: IssuePayload

    @staticmethod
    def fake() -> IssueRead:
        return IssueRead(issue=IssuePayload.fake())


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


class IssueEdited(Payload):
    url: IssueUrl = Field(validation_alias=AliasPath("issueUpdate", "issue", "url"))

    @staticmethod
    def fake() -> IssueEdited:
        return IssueEdited(url=IssueUrl.fake())


class ProjectOfIssue(Payload):
    project: ProjectId | None = Field(
        default=None, validation_alias=AliasPath("issue", "project", "id")
    )

    @staticmethod
    def fake() -> ProjectOfIssue:
        return ProjectOfIssue(project=ProjectId.fake())


class MilestoneNode(Payload):
    id: MilestoneId
    name: MilestoneName

    @staticmethod
    def fake() -> MilestoneNode:
        return MilestoneNode(id=MilestoneId.fake(), name=MilestoneName.fake())


class ProjectMilestones(Payload):
    milestones: tuple[MilestoneNode, ...] = Field(
        validation_alias=AliasPath("project", "projectMilestones", "nodes")
    )

    @staticmethod
    def fake() -> ProjectMilestones:
        return ProjectMilestones(milestones=(MilestoneNode.fake(),))

    # Linear resolves labels and projects by name ignoring case, so milestones follow suit.
    def named(self, milestone: MilestoneName) -> MilestoneId | None:
        wanted = milestone.root.casefold()
        return next(
            (node.id for node in self.milestones if node.name.root.casefold() == wanted), None
        )


ISSUE_FIELDS = """
    identifier
    title
    description
    state { name }
    project { name }
    projectMilestone { name }
    labels { nodes { name } }
    assignee { email }
"""


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
                        nodes {"""
                    + ISSUE_FIELDS
                    + """}
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
        with translated_errors():
            data = self._client.execute(
                """
                query($id: String!) {
                  issue(id: $id) {"""
                + ISSUE_FIELDS
                + """}
                }
                """,
                {"id": issue.root},
            )
        return IssueRead.model_validate(data).issue.issue()

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
        user = self._user_id(assignee)
        with translated_errors():
            _ = self._client.update_issue(IssueUpdateRequest(id=issue.root, assignee_id=user.root))

    @override
    def viewer(self) -> Assignee:
        with translated_errors():
            found = self._client.viewer().viewer
        if found is None or found.email is None:
            raise IssueTrackerError("Linear did not say who the API key belongs to.")
        return Assignee(found.email)

    # The client's update request drops None fields, and clearing a field needs an explicit null.
    @override
    def edit(self, issue: IssueIdentifier, change: IssueEdit) -> IssueUrl:
        fields: dict[str, object] = {}
        if change.title is not None:
            fields["title"] = change.title.root
        if change.body is not None:
            fields["description"] = change.body.root
        if change.added_labels.root:
            fields["addedLabelIds"] = [
                self._label_id(label).root for label in change.added_labels.root
            ]
        if change.removed_labels.root:
            fields["removedLabelIds"] = [
                self._label_id(label).root for label in change.removed_labels.root
            ]
        if change.assignee is not None:
            fields["assigneeId"] = (
                None if isinstance(change.assignee, Clear) else self._user_id(change.assignee).root
            )
        if change.project is not None:
            fields["projectId"] = (
                None if isinstance(change.project, Clear) else self._project_id(change.project).root
            )
        if change.milestone is not None:
            fields["projectMilestoneId"] = (
                None
                if isinstance(change.milestone, Clear)
                else self._milestone_id(issue, change, change.milestone).root
            )
        with translated_errors():
            data = self._client.execute(
                """
                mutation($id: String!, $input: IssueUpdateInput!) {
                  issueUpdate(id: $id, input: $input) { issue { url } }
                }
                """,
                {"id": issue.root, "input": fields},
            )
        return IssueEdited.model_validate(data).url

    def _user_id(self, assignee: Assignee) -> UserId:
        with translated_errors():
            user = self._client.find_user(FindUserRequest(email=assignee.root)).user
        if user is None or user.id is None:
            raise IssueTrackerError(f"No Linear user has the email {assignee.root}.")
        return UserId(user.id)

    def _project_id(self, project: ProjectName) -> ProjectId:
        with translated_errors():
            found = self._client.find_project(FindProjectRequest(name=project.root)).project
        if found is None or found.id is None:
            raise IssueTrackerError(f"No project is named {project.root}.")
        return ProjectId(found.id)

    # A milestone belongs to a project: the one this edit moves the issue to, else its current one.
    def _milestone_id(
        self, issue: IssueIdentifier, change: IssueEdit, milestone: MilestoneName
    ) -> MilestoneId:
        project = (
            self._project_id(change.project)
            if isinstance(change.project, ProjectName)
            else self._current_project(issue)
        )
        if project is None:
            raise IssueTrackerError(f"{issue.root} is in no project, so it can take no milestone.")
        with translated_errors():
            data = self._client.execute(
                """
                query($id: String!) {
                  project(id: $id) { projectMilestones { nodes { id name } } }
                }
                """,
                {"id": project.root},
            )
        found = ProjectMilestones.model_validate(data).named(milestone)
        if found is None:
            raise IssueTrackerError(f"The project has no milestone named {milestone.root}.")
        return found

    def _current_project(self, issue: IssueIdentifier) -> ProjectId | None:
        with translated_errors():
            data = self._client.execute(
                "query($id: String!) { issue(id: $id) { project { id } } }", {"id": issue.root}
            )
        return ProjectOfIssue.model_validate(data).project

    def _label_id(self, label: LabelName) -> LabelId:
        with translated_errors():
            found = self._client.find_label(FindLabelRequest(name=label.root)).label
        if found is None or found.id is None:
            raise IssueTrackerError(f"No label is named {label.root}.")
        return LabelId(found.id)
