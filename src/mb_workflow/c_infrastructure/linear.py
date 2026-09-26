import os
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
    Issue,
    IssueIdentifier,
    Issues,
    LabelName,
    LabelNames,
    ProjectName,
    StatusName,
)
from mb_workflow.d_lib.models import Payload, Value

if TYPE_CHECKING:
    from collections.abc import Generator

    from mb_workflow.b_core.d_domain_model.issue import Assignee, IssueFilter


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


# Only whether someone is assigned matters, so none of the assignee's fields are read.
class AssigneePayload(Payload):
    @staticmethod
    def fake() -> AssigneePayload:
        return AssigneePayload()


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
        with translated_errors():
            data = self._client.execute(
                """
                query($id: String!) {
                  issue(id: $id) {
                    identifier
                    state { name }
                    project { name }
                    labels { nodes { name } }
                    assignee { id }
                  }
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
        with translated_errors():
            user = self._client.find_user(FindUserRequest(email=assignee.root)).user
            if user is None or user.id is None:
                raise IssueTrackerError(f"No Linear user has the email {assignee.root}.")
            _ = self._client.update_issue(IssueUpdateRequest(id=issue.root, assignee_id=user.id))

    def _label_id(self, label: LabelName) -> LabelId:
        with translated_errors():
            found = self._client.find_label(FindLabelRequest(name=label.root)).label
        if found is None or found.id is None:
            raise IssueTrackerError(f"No label is named {label.root}.")
        return LabelId(found.id)
