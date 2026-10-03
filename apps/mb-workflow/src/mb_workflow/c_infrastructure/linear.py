from contextlib import contextmanager
from enum import StrEnum
from typing import TYPE_CHECKING, override

from linear_python_client import (
    FindUserRequest,
    IssueAddLabelRequest,
    IssueLabelsRequest,
    IssueRemoveLabelRequest,
    IssueUpdateRequest,
    LinearClient,
    LinearError,
)
from pydantic import AliasPath, Field, JsonValue

from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker, TicketTrackerError
from mb_workflow.b_core.d_domain_model.issue import (
    Assigned,
    Assignee,
    Cleared,
    ColoredLabel,
    ColoredLabels,
    CreatedIssue,
    GroupedLabel,
    GroupedLabels,
    Issue,
    IssueDescription,
    IssueDetail,
    IssueIdentifier,
    Issues,
    IssueStatusName,
    IssueTitle,
    IssueUpdate,
    IssueUrl,
    LabelColor,
    LabelGroupName,
    LabelName,
    LabelNames,
    Milestone,
    MilestoneName,
    NewIssue,
    ProjectName,
    TeamKey,
    TeamName,
)
from mb_workflow.b_core.d_domain_model.pool import PoolTicket, PoolTickets, Priority
from mb_workflow.d_lib.models import Payload, Value

if TYPE_CHECKING:
    from collections.abc import Generator

    from mb_workflow.b_core.d_domain_model.issue import IssueFilter, StatusTypes
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


class LabelParentPayload(Payload):
    name: LabelGroupName

    @staticmethod
    def fake() -> LabelParentPayload:
        return LabelParentPayload(name=LabelGroupName.fake())


class LabelPayload(Payload):
    name: LabelName
    parent: LabelParentPayload | None = None

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
    team: TeamKey | None = Field(default=None, validation_alias=AliasPath("team", "key"))

    @staticmethod
    def fake() -> LabelRecord:
        return LabelRecord(id=LabelId.fake(), name=LabelName.fake(), team=None)


class GroupedLabelRecord(Payload):
    id: LabelId
    name: LabelName
    color: LabelColor

    @staticmethod
    def fake() -> GroupedLabelRecord:
        return GroupedLabelRecord(id=LabelId.fake(), name=LabelName.fake(), color=LabelColor.fake())


class LabelGroupRecord(Payload):
    id: LabelId
    children: tuple[GroupedLabelRecord, ...] = Field(
        default=(), validation_alias=AliasPath("children", "nodes")
    )

    @staticmethod
    def fake() -> LabelGroupRecord:
        return LabelGroupRecord(id=LabelId.fake(), children=(GroupedLabelRecord.fake(),))

    def labels(self) -> ColoredLabels:
        return ColoredLabels(
            tuple(ColoredLabel(name=child.name, color=child.color) for child in self.children)
        )


class LabelGroupRead(Payload):
    groups: tuple[LabelGroupRecord, ...] = Field(validation_alias=AliasPath("issueLabels", "nodes"))

    @staticmethod
    def fake() -> LabelGroupRead:
        return LabelGroupRead(groups=(LabelGroupRecord.fake(),))


class TeamRead(Payload):
    teams: tuple[TeamRecord, ...] = Field(validation_alias=AliasPath("teams", "nodes"))

    @staticmethod
    def fake() -> TeamRead:
        return TeamRead(teams=(TeamRecord.fake(),))


class IssueTeamRead(Payload):
    team: TeamKey = Field(validation_alias=AliasPath("issue", "team", "key"))

    @staticmethod
    def fake() -> IssueTeamRead:
        return IssueTeamRead(team=TeamKey.fake())


class LabelParentRead(Payload):
    labels: tuple[LabelPayload, ...] = Field(validation_alias=AliasPath("issueLabels", "nodes"))

    @staticmethod
    def fake() -> LabelParentRead:
        return LabelParentRead(labels=(LabelPayload.fake(),))

    def group(self) -> LabelGroupName | None:
        parent = self.labels[0].parent if self.labels else None
        return parent.name if parent is not None else None


class CreatedLabel(Payload):
    id: LabelId = Field(validation_alias=AliasPath("issueLabelCreate", "issueLabel", "id"))

    @staticmethod
    def fake() -> CreatedLabel:
        return CreatedLabel(id=LabelId.fake())


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
    issue_team: TeamKey | None = Field(
        default=None, validation_alias=AliasPath("issue", "team", "key")
    )

    @staticmethod
    def fake() -> UpdateLookup:
        return UpdateLookup(
            labels=(LabelRecord.fake(),),
            users=(UserRecord.fake(),),
            projects=(ProjectRecord.fake(),),
            milestone_projects=(ProjectRecord.fake(),),
            states=(StateRecord.fake(),),
            issue_team=TeamKey.fake(),
        )

    # Teams may each hold a label of the same name, so the issue's own team's one wins, then the workspace's.
    def label_ids(self, labels: LabelNames, team: TeamKey | None) -> tuple[LabelId, ...]:
        own = tuple(
            record
            for record in self.labels
            if record.team is not None and team is not None and record.team.names(team).root
        )
        usable = (*own, *(record for record in self.labels if record.team is None))
        known = LabelNames(tuple(record.name for record in usable))
        unknown = known.unmatched(labels)
        if unknown.root:
            raise TicketTrackerError(
                f"No label is named {', '.join(label.root for label in unknown.root)}."
            )
        return tuple(
            next(record.id for record in usable if record.name == name)
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


class TeamId(Value[str]):
    @staticmethod
    def fake() -> TeamId:
        return TeamId("6f3c5a4e-1f0b-4b8e-9d7a-2c1e0f9b8a7d")


class TeamRecord(Payload):
    id: TeamId
    key: TeamKey
    states: tuple[StateRecord, ...] = Field(
        default=(), validation_alias=AliasPath("states", "nodes")
    )

    @staticmethod
    def fake() -> TeamRecord:
        return TeamRecord(id=TeamId.fake(), key=TeamKey.fake(), states=(StateRecord.fake(),))

    def state_id(self, status: IssueStatusName) -> StateId:
        found = next((known for known in self.states if known.name.names(status).root), None)
        if found is None:
            raise TicketTrackerError(f"{self.key.root} has no status named {status.root}.")
        return found.id


class TeamProjectRecord(ProjectRecord):
    teams: tuple[TeamRecord, ...] = Field(default=(), validation_alias=AliasPath("teams", "nodes"))

    @override
    @staticmethod
    def fake() -> TeamProjectRecord:
        return TeamProjectRecord(
            id=ProjectId.fake(),
            name=ProjectName.fake(),
            milestones=(MilestoneRecord.fake(),),
            teams=(TeamRecord.fake(),),
        )


# Resolves every name a new issue carries in one read, the team coming from the project if unnamed.
class CreationLookup(UpdateLookup):
    projects: tuple[TeamProjectRecord, ...] = Field(
        default=(), validation_alias=AliasPath("project", "nodes")
    )
    teams: tuple[TeamRecord, ...] = Field(default=(), validation_alias=AliasPath("team", "nodes"))

    @override
    @staticmethod
    def fake() -> CreationLookup:
        return CreationLookup(
            labels=(LabelRecord.fake(),),
            users=(UserRecord.fake(),),
            projects=(TeamProjectRecord.fake(),),
            teams=(TeamRecord.fake(),),
        )

    def creation(self, new: NewIssue) -> IssueCreation:
        project = self._project(new.project) if new.project is not None else None
        team = self._team(new.team, project)
        return IssueCreation(
            team_id=team.id,
            title=new.title,
            description=new.description,
            label_ids=self.label_ids(new.labels, team.key),
            assignee_id=self.user_id(new.assignee) if new.assignee is not None else None,
            project_id=project.id if project is not None else None,
            state_id=team.state_id(new.status),
            project_milestone_id=(
                project.milestone(new.milestone.name)
                if project is not None and new.milestone is not None
                else None
            ),
        )

    def _project(self, name: ProjectName) -> TeamProjectRecord:
        if not self.projects:
            raise TicketTrackerError(f"No project is named {name.root}.")
        return self.projects[0]

    def _team(self, key: TeamKey | None, project: TeamProjectRecord | None) -> TeamRecord:
        if key is not None:
            if not self.teams:
                raise TicketTrackerError(f"No team has the key {key.root}.")
            return self.teams[0]
        if project is None:
            raise TicketTrackerError("Name a team or a project to create the issue in.")
        if len(project.teams) != 1:
            raise TicketTrackerError(
                f"{project.name.root} belongs to several teams. Set [issues] team to pick one."
            )
        return project.teams[0]


class IssueCreation(Payload):
    team_id: TeamId
    title: IssueTitle
    description: IssueDescription | None
    label_ids: tuple[LabelId, ...]
    assignee_id: UserId | None
    project_id: ProjectId | None
    state_id: StateId
    project_milestone_id: MilestoneId | None

    @staticmethod
    def fake() -> IssueCreation:
        return IssueCreation(
            team_id=TeamId.fake(),
            title=IssueTitle.fake(),
            description=None,
            label_ids=(),
            assignee_id=None,
            project_id=None,
            state_id=StateId.fake(),
            project_milestone_id=None,
        )


class CreatedIssueRead(Payload):
    identifier: IssueIdentifier = Field(
        validation_alias=AliasPath("issueCreate", "issue", "identifier")
    )
    url: IssueUrl = Field(validation_alias=AliasPath("issueCreate", "issue", "url"))

    @staticmethod
    def fake() -> CreatedIssueRead:
        return CreatedIssueRead(identifier=IssueIdentifier.fake(), url=IssueUrl.fake())

    def created(self) -> CreatedIssue:
        return CreatedIssue(identifier=self.identifier, url=self.url)


class RelationType(StrEnum):
    blocks = "blocks"
    duplicate = "duplicate"
    related = "related"
    similar = "similar"


class InverseRelation(Payload):
    type: RelationType
    identifier: IssueIdentifier = Field(validation_alias=AliasPath("issue", "identifier"))

    @staticmethod
    def fake() -> InverseRelation:
        return InverseRelation(type=RelationType.blocks, identifier=IssueIdentifier.fake())


class Relation(Payload):
    type: RelationType
    identifier: IssueIdentifier = Field(validation_alias=AliasPath("relatedIssue", "identifier"))

    @staticmethod
    def fake() -> Relation:
        return Relation(type=RelationType.blocks, identifier=IssueIdentifier.fake())


class InverseRelationsRead(Payload):
    relations: tuple[InverseRelation, ...] = Field(
        validation_alias=AliasPath("issue", "inverseRelations", "nodes")
    )

    @staticmethod
    def fake() -> InverseRelationsRead:
        return InverseRelationsRead(relations=(InverseRelation.fake(),))

    def blockers(self) -> tuple[IssueIdentifier, ...]:
        return tuple(
            relation.identifier
            for relation in self.relations
            if relation.type == RelationType.blocks
        )


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
            grouped=GroupedLabels(
                tuple(
                    GroupedLabel(group=label.parent.name, label=label.name)
                    for label in self.labels
                    if label.parent is not None
                )
            ),
            assigned=Assigned(self.assignee is not None),
        )


class PoolTicketPayload(IssuePayload):
    priority: Priority

    @override
    @staticmethod
    def fake() -> PoolTicketPayload:
        return PoolTicketPayload(
            identifier=IssueIdentifier.fake(),
            status=IssueStatusName.fake(),
            project=ProjectPayload.fake(),
            labels=(LabelPayload.fake(),),
            priority=Priority.medium,
        )

    def ticket(self) -> PoolTicket:
        return PoolTicket(issue=self.issue(), priority=self.priority)


class IssueDetailPayload(IssuePayload):
    title: IssueTitle
    description: IssueDescription | None = None
    milestone: MilestonePayload | None = Field(default=None, validation_alias="projectMilestone")
    relations: tuple[Relation, ...] = Field(validation_alias=AliasPath("relations", "nodes"))
    inverse_relations: tuple[InverseRelation, ...] = Field(
        validation_alias=AliasPath("inverseRelations", "nodes")
    )

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
            relations=(Relation.fake(),),
            inverse_relations=(InverseRelation.fake(),),
        )

    def detail(self) -> IssueDetail:
        return IssueDetail(
            issue=self.issue(),
            title=self.title,
            description=self.description,
            assignee=self.assignee.email if self.assignee is not None else None,
            milestone=self.milestone.name if self.milestone is not None else None,
            blocks=frozenset(
                relation.identifier
                for relation in self.relations
                if relation.type == RelationType.blocks
            ),
            blocked_by=frozenset(
                relation.identifier
                for relation in self.inverse_relations
                if relation.type == RelationType.blocks
            ),
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
    def group_labels(self, group: LabelGroupName, team: TeamKey | None) -> ColoredLabels:
        found = self._found_group(group, team)
        return found.labels() if found is not None else ColoredLabels(())

    @override
    def label_group(self, label: LabelName) -> LabelGroupName | None:
        with translated_errors():
            data = self._client.execute(
                """
                query($name: String!) {
                  issueLabels(first: 1, filter: { name: { eqIgnoreCase: $name }, isGroup: { eq: false } }) {
                    nodes { name parent { name } }
                  }
                }
                """,
                {"name": label.root},
            )
        return LabelParentRead.model_validate(data).group()

    @override
    def create_group_labels(
        self, group: LabelGroupName, labels: ColoredLabels, team: TeamKey | None
    ) -> None:
        found = self._found_group(group, team)
        owner = {"teamId": self._team_id(team).root} if team is not None else {}
        parent = (
            found.id
            if found is not None
            else self._created_label(
                {"name": group.root, "isGroup": True, "groupType": "singleSelect", **owner}
            )
        )
        for label in labels.root:
            _ = self._created_label(
                {
                    "name": label.name.root,
                    "color": label.color.root,
                    "parentId": parent.root,
                    **owner,
                }
            )

    @override
    def recolor_group_labels(
        self, group: LabelGroupName, labels: ColoredLabels, team: TeamKey | None
    ) -> None:
        found = self._found_group(group, team)
        children = found.children if found is not None else ()
        for label in labels.root:
            child = next(
                (
                    child
                    for child in children
                    if child.name.root.casefold() == label.name.root.casefold()
                ),
                None,
            )
            if child is None:
                raise TicketTrackerError(
                    f"The {group.root} group holds no label named {label.name.root}."
                )
            with translated_errors():
                _ = self._client.execute(
                    "mutation($id: String!, $input: IssueLabelUpdateInput!) {"
                    " issueLabelUpdate(id: $id, input: $input) { success } }",
                    {"id": child.id.root, "input": {"color": label.color.root}},
                )

    @override
    def team_named(self, name: TeamName) -> TeamKey:
        found = self._found_team({"name": {"eqIgnoreCase": name.root}})
        if found is None:
            raise TicketTrackerError(f"No team is named {name.root}.")
        return found.key

    @override
    def team_of(self, issue: IssueIdentifier) -> TeamKey:
        with translated_errors():
            data = self._client.execute(
                "query($id: String!) { issue(id: $id) { team { key } } }", {"id": issue.root}
            )
        return IssueTeamRead.model_validate(data).team

    def _team_id(self, team: TeamKey) -> TeamId:
        found = self._found_team({"key": {"eqIgnoreCase": team.root}})
        if found is None:
            raise TicketTrackerError(f"No team has the key {team.root}.")
        return found.id

    def _found_team(self, team_filter: JsonValue) -> TeamRecord | None:
        with translated_errors():
            data = self._client.execute(
                "query($filter: TeamFilter!) {"
                " teams(first: 1, filter: $filter) { nodes { id key } } }",
                {"filter": team_filter},
            )
        teams = TeamRead.model_validate(data).teams
        return teams[0] if teams else None

    def _found_group(self, group: LabelGroupName, team: TeamKey | None) -> LabelGroupRecord | None:
        with translated_errors():
            data = self._client.execute(
                """
                query($name: String!, $team: NullableTeamFilter!) {
                  issueLabels(
                    first: 1
                    filter: { name: { eqIgnoreCase: $name }, isGroup: { eq: true }, team: $team }
                  ) {
                    nodes { id children(first: 250) { nodes { id name color } } }
                  }
                }
                """,
                {
                    "name": group.root,
                    "team": {"null": True}
                    if team is None
                    else {"key": {"eqIgnoreCase": team.root}},
                },
            )
        groups = LabelGroupRead.model_validate(data).groups
        return groups[0] if groups else None

    def _created_label(self, label: JsonValue) -> LabelId:
        with translated_errors():
            data = self._client.execute(
                "mutation($input: IssueLabelCreateInput!) {"
                " issueLabelCreate(input: $input) { issueLabel { id } } }",
                {"input": label},
            )
        return CreatedLabel.model_validate(data).id

    @override
    def list_issues(self, wanted: IssueFilter) -> Issues:
        return self._issues_matching(
            {
                "creator": {"email": {"eq": wanted.creator.root}},
                "createdAt": {"gte": wanted.created_after.root.isoformat()},
            }
        )

    @override
    def labelled_issues(self, label: LabelName, excluding: StatusTypes) -> Issues:
        return self._issues_matching(
            {
                "labels": {"some": {"name": {"eqIgnoreCase": label.root}}},
                "state": {"type": {"nin": [status_type.value for status_type in excluding.root]}},
            }
        )

    def _issues_matching(self, issue_filter: JsonValue) -> Issues:
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
                          labels { nodes { name parent { name } } }
                          assignee { id }
                        }
                        pageInfo { hasNextPage endCursor }
                      }
                    }
                    """,
                    {
                        "filter": issue_filter,
                        "after": cursor.root if cursor is not None else None,
                    },
                )
            page = IssueSweep.model_validate(data).issues
            found.extend(page.issues().root)
            cursor = page.page_info.next_cursor()
            if cursor is None:
                return Issues(tuple(found))

    @override
    def unblocked_view_tickets(self, view: ViewSlug) -> PoolTickets:
        found: list[PoolTicket] = []
        cursor: PageCursor | None = None
        while True:
            with translated_errors():
                data = self._client.execute(
                    """
                    query($view: String!, $after: String) {
                      customView(id: $view) {
                        issues(
                          first: 250
                          after: $after
                          filter: { hasBlockedByRelations: { eq: false } }
                        ) {
                          nodes {
                            identifier
                            priority
                            state { name }
                            project { name }
                            labels { nodes { name parent { name } } }
                            assignee { id }
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
                    labels { nodes { name parent { name } } }
                    assignee { email }
                    projectMilestone { name }
                    relations(first: 250) { nodes { type relatedIssue { identifier } } }
                    inverseRelations(first: 250) { nodes { type issue { identifier } } }
                  }
                }
                """,
                {"id": issue.root},
            )
        return IssueDetailRead.model_validate(data).issue.detail()

    @override
    def add_label(self, issue: IssueIdentifier, label: LabelName) -> None:
        (label_id,) = self._label_ids(issue, LabelNames((label,)))
        with translated_errors():
            _ = self._client.add_label(IssueAddLabelRequest(id=issue.root, label_id=label_id.root))

    @override
    def remove_label(self, issue: IssueIdentifier, label: LabelName) -> None:
        (label_id,) = self._label_ids(issue, LabelNames((label,)))
        with translated_errors():
            _ = self._client.remove_label(
                IssueRemoveLabelRequest(id=issue.root, label_id=label_id.root)
            )

    @override
    def set_labels(self, issue: IssueIdentifier, labels: LabelNames) -> None:
        label_ids = [label_id.root for label_id in self._label_ids(issue, labels)]
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
            changes["label_ids"] = found.label_ids(update.labels, found.issue_team)
        if update.assignee is not None:
            changes["assignee_id"] = found.user_id(update.assignee)
        if update.project is not None:
            changes["project_id"] = found.project_id(update.project)
        if update.status is not None:
            changes["state_id"] = found.state_id(update.status)
        if update.milestone is not None:
            changes["project_milestone_id"] = found.milestone_id(update.milestone)
        if changes:
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
        for blocked in update.blocks:
            self._relate(blocker=issue, blocked=blocked)
        for blocker in update.blocked_by:
            self._relate(blocker=blocker, blocked=issue)

    @override
    def create_issue(self, new: NewIssue) -> CreatedIssue:
        creation = self._creation_lookup(new).creation(new)
        with translated_errors():
            data = self._client.execute(
                "mutation($input: IssueCreateInput!) {"
                " issueCreate(input: $input) { issue { identifier url } } }",
                {"input": creation.model_dump(mode="json", by_alias=True, exclude_none=True)},
            )
        created = CreatedIssueRead.model_validate(data).created()
        for blocked in new.blocks:
            self._relate(blocker=created.identifier, blocked=blocked)
        for blocker in new.blocked_by:
            self._relate(blocker=blocker, blocked=created.identifier)
        return created

    @override
    def blockers(self, issue: IssueIdentifier) -> tuple[IssueIdentifier, ...]:
        with translated_errors():
            data = self._client.execute(
                """
                query($id: String!) {
                  issue(id: $id) {
                    inverseRelations(first: 250) { nodes { type issue { identifier } } }
                  }
                }
                """,
                {"id": issue.root},
            )
        return InverseRelationsRead.model_validate(data).blockers()

    def _relate(self, *, blocker: IssueIdentifier, blocked: IssueIdentifier) -> None:
        with translated_errors():
            _ = self._client.execute(
                "mutation($input: IssueRelationCreateInput!) {"
                " issueRelationCreate(input: $input) { success } }",
                {
                    "input": {
                        "issueId": blocker.root,
                        "relatedIssueId": blocked.root,
                        "type": RelationType.blocks.value,
                    }
                },
            )

    def _creation_lookup(self, new: NewIssue) -> CreationLookup:
        with translated_errors():
            data = self._client.execute(
                """
                query(
                  $labels: IssueLabelFilter, $withLabels: Boolean!
                  $user: UserFilter, $withUser: Boolean!
                  $project: ProjectFilter, $withProject: Boolean!
                  $team: TeamFilter, $withTeam: Boolean!
                ) {
                  issueLabels(first: 250, filter: $labels) @include(if: $withLabels) {
                    nodes { id name team { key } }
                  }
                  users(first: 1, filter: $user) @include(if: $withUser) { nodes { id } }
                  project: projects(first: 1, filter: $project) @include(if: $withProject) {
                    nodes {
                      id
                      name
                      projectMilestones { nodes { id name } }
                      teams(first: 2) { nodes { id key states(first: 100) { nodes { id name } } } }
                    }
                  }
                  team: teams(first: 1, filter: $team) @include(if: $withTeam) {
                    nodes { id key states(first: 100) { nodes { id name } } }
                  }
                }
                """,
                {
                    "labels": {
                        "or": [{"name": {"eqIgnoreCase": label.root}} for label in new.labels.root]
                    },
                    "withLabels": bool(new.labels.root),
                    "user": {"email": {"eq": new.assignee.root}} if new.assignee else None,
                    "withUser": new.assignee is not None,
                    "project": {"name": {"eqIgnoreCase": new.project.root}}
                    if new.project
                    else None,
                    "withProject": new.project is not None,
                    "team": {"key": {"eqIgnoreCase": new.team.root}} if new.team else None,
                    "withTeam": new.team is not None,
                },
            )
        return CreationLookup.model_validate(data)

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
                  $withTeam: Boolean!, $withStates: Boolean!
                ) {
                  issueLabels(first: 250, filter: $labels) @include(if: $withLabels) {
                    nodes { id name team { key } }
                  }
                  users(first: 1, filter: $user) @include(if: $withUser) { nodes { id } }
                  project: projects(first: 1, filter: $project) @include(if: $withProject) {
                    nodes { id name }
                  }
                  milestoneProject: projects(first: 1, filter: $milestoneProject)
                    @include(if: $withMilestone) {
                    nodes { id name projectMilestones { nodes { id name } } }
                  }
                  issue(id: $issue) @include(if: $withTeam) {
                    team {
                      key
                      states(first: 250) @include(if: $withStates) { nodes { id name } }
                    }
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
                    "withTeam": bool(labels) or update.status is not None,
                    "withStates": update.status is not None,
                },
            )
        return UpdateLookup.model_validate(data)

    def _label_ids(self, issue: IssueIdentifier, labels: LabelNames) -> tuple[LabelId, ...]:
        found = self._lookup(issue, IssueUpdate.nothing().model_copy(update={"labels": labels}))
        return found.label_ids(labels, found.issue_team)
