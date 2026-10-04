import re
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, override

import pytest
from linear_python_client import (
    FindProjectRequest,
    IssueCreateRequest,
    IssueLabelsRequest,
    IssuesRequest,
    LinearClient,
)
from pydantic import AliasPath, Field
from safe_result import Err, Ok

from mb_workflow.b_core.c_secondary_ports.claims import (
    Claiming,
    ClaimLostError,
    ClaimRegistry,
    ClaimRequest,
    FakeClaimRegistry,
)
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
    FakeTicketTracker,
    TicketTrackerError,
    TrackedIssue,
)
from mb_workflow.b_core.d_domain_model.claim import ClaimHolder, ClaimId, Claims, HostName
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
from mb_workflow.b_core.d_domain_model.issue import (
    Assigned,
    Assignee,
    Cleared,
    ColoredLabel,
    ColoredLabels,
    CreatedAfter,
    CreatedIssue,
    CreatedOn,
    Creator,
    GroupedLabels,
    Issue,
    IssueDescription,
    IssueDetail,
    IssueFilter,
    IssueIdentifier,
    IssueStatus,
    IssueStatuses,
    IssueStatusName,
    IssueTitle,
    IssueUpdate,
    LabelColor,
    LabelGroupName,
    LabelName,
    LabelNames,
    Milestone,
    MilestoneName,
    MilestoneNames,
    NewIssue,
    Priority,
    Project,
    ProjectName,
    Projects,
    StatusType,
    StatusTypes,
    Team,
    TeamKey,
    TeamName,
    TicketCount,
)
from mb_workflow.b_core.d_domain_model.pool import PoolTicket, ViewSlug
from mb_workflow.c_infrastructure.credentials import CredentialsDirectory, RepositorySlug
from mb_workflow.c_infrastructure.linear import (
    LabelGroupRead,
    Linear,
    MilestonePayload,
    ProjectId,
    TeamId,
)
from mb_workflow.c_infrastructure.linear_claims import LinearClaims
from mb_workflow.c_infrastructure.shell import ExistingDirectory, Shell
from mb_workflow.d_lib.models import Model, Payload, Value

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from safe_result import Result

    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker

    type Creating = Callable[[NewIssue], Result[CreatedIssue, TicketTrackerError]]


class Seed(StrEnum):
    recent = "recent"
    old = "old"
    newest = "newest"
    done = "done"


class SeededIssue(Model):
    seed: Seed
    created_on: CreatedOn
    status: IssueStatusName
    project: ProjectName | None
    labels: LabelNames
    description: IssueDescription | None
    priority: Priority
    blocked_by: tuple[Seed, ...]

    def issue(self, identifier: IssueIdentifier) -> Issue:
        return Issue(
            identifier=identifier,
            status=self.status,
            project=self.project,
            labels=self.labels,
            grouped=GroupedLabels(()),
            assigned=Assigned(False),
        )

    def title(self) -> IssueTitle:
        return IssueTitle(f"contract: {self.seed.value}")

    def detail(
        self,
        identifier: IssueIdentifier,
        blocks: frozenset[IssueIdentifier],
        blocked_by: frozenset[IssueIdentifier],
    ) -> IssueDetail:
        return IssueDetail(
            issue=self.issue(identifier),
            title=self.title(),
            description=self.description,
            assignee=None,
            milestone=None,
            blocks=blocks,
            blocked_by=blocked_by,
        )


def workspace_labels() -> LabelNames:
    return LabelNames(tuple(LabelName(name) for name in ("Backend", "d-grill", "d-implement")))


def seeded(
    seed: Seed, created: CreatedOn, priority: Priority, blocked_by: tuple[Seed, ...] = ()
) -> SeededIssue:
    return SeededIssue(
        seed=seed,
        created_on=created,
        status=IssueStatusName.fake(),
        project=ProjectName.fake(),
        labels=LabelNames(()),
        description=IssueDescription.fake(),
        priority=priority,
        blocked_by=blocked_by,
    )


def seeds() -> tuple[SeededIssue, ...]:
    return (
        seeded(
            Seed.recent,
            CreatedOn(date(2026, 9, 1)),
            Priority.urgent,
            blocked_by=(Seed.old, Seed.done),
        ),
        seeded(Seed.old, CreatedOn(date(2026, 8, 1)), Priority.low),
        seeded(Seed.newest, CreatedOn(date(2026, 9, 2)), Priority.no_priority),
        SeededIssue(
            seed=Seed.done,
            created_on=CreatedOn.fake(),
            status=IssueStatusName("Done"),
            project=None,
            labels=LabelNames((LabelName("d-grill"),)),
            description=None,
            priority=Priority.high,
            blocked_by=(),
        ),
    )


class Backlog(Model):
    identifiers: dict[Seed, IssueIdentifier]
    creator: Creator
    assignee: Assignee
    view: ViewSlug
    team: TeamKey
    team_name: TeamName
    other_team: TeamKey
    other_team_name: TeamName

    def identifier(self, seed: Seed) -> IssueIdentifier:
        return self.identifiers[seed]

    def issue(self, seed: Seed) -> Issue:
        return self.detail(seed).issue

    def detail(self, seed: Seed) -> IssueDetail:
        planted = next(planted for planted in seeds() if planted.seed == seed)
        return planted.detail(
            self.identifier(seed),
            blocks=frozenset(
                self.identifier(other.seed) for other in seeds() if seed in other.blocked_by
            ),
            blocked_by=frozenset(self.identifier(blocker) for blocker in planted.blocked_by),
        )

    def ticket(self, seed: Seed) -> PoolTicket:
        planted = next(planted for planted in seeds() if planted.seed == seed)
        return PoolTicket(
            issue=self.issue(seed),
            priority=planted.priority,
        )

    def picked(self, wanted: IssueFilter, tracker: TicketTracker) -> tuple[Seed, ...]:
        swept = tracker.list_issues(wanted).unwrap().identifiers()
        return tuple(seed for seed in Seed if self.identifier(seed) in swept)


class WorkspaceKey(Value[str]):
    @staticmethod
    def fake() -> WorkspaceKey:
        return WorkspaceKey("mb-workflow-integration-test")


class Organization(Payload):
    url_key: WorkspaceKey

    @staticmethod
    def fake() -> Organization:
        return Organization(url_key=WorkspaceKey.fake())


class WorkspaceTeam(Payload):
    id: TeamId
    key: TeamKey
    name: TeamName

    @staticmethod
    def fake() -> WorkspaceTeam:
        return WorkspaceTeam(id=TeamId.fake(), key=TeamKey.fake(), name=TeamName.fake())

    # Team-scoped labels are only told apart with a second team, which the suite keeps for that.
    @staticmethod
    def other() -> WorkspaceTeam:
        return WorkspaceTeam(id=TeamId.fake(), key=TeamKey("CON"), name=TeamName("Contract"))


class Workspace(Payload):
    organization: Organization
    teams: tuple[WorkspaceTeam, ...] = Field(validation_alias=AliasPath("teams", "nodes"))

    @staticmethod
    def fake() -> Workspace:
        return Workspace(organization=Organization.fake(), teams=(WorkspaceTeam.fake(),))

    @staticmethod
    def of(client: LinearClient) -> Workspace:
        return Workspace.model_validate(
            client.execute("{ organization { urlKey } teams { nodes { id key name } } }")
        )

    @staticmethod
    def ensure_other_team(client: LinearClient) -> WorkspaceTeam:
        wanted = WorkspaceTeam.other()
        found = next((team for team in Workspace.of(client).teams if team.key == wanted.key), None)
        if found is not None:
            return found
        _ = client.execute(
            "mutation($input: TeamCreateInput!) { teamCreate(input: $input) { success } }",
            {"input": {"name": wanted.name.root, "key": wanted.key.root}},
        )
        return next(team for team in Workspace.of(client).teams if team.key == wanted.key)


class TrackerKind(StrEnum):
    fake = "fake"
    linear = "linear"


def fake_backlog() -> Backlog:
    return Backlog(
        identifiers={seed: IssueIdentifier(f"E-{n}") for n, seed in enumerate(Seed, start=1)},
        creator=Creator.fake(),
        assignee=Assignee.fake(),
        view=ViewSlug.fake(),
        team=TeamKey.fake(),
        team_name=TeamName.fake(),
        other_team=WorkspaceTeam.other().key,
        other_team_name=WorkspaceTeam.other().name,
    )


# A key for the production workspace would make this suite rewrite real issues.
@pytest.fixture(scope="session")
def linear_client() -> LinearClient:
    path = CredentialsDirectory.of_user().path_for(
        RepositorySlug.of_origin(Shell(ExistingDirectory(Path.cwd()))).unwrap()
    )
    key = path.credentials().unwrap().linear.integration_test_api_key
    if key is None:
        pytest.fail(f"Set [linear] integration_test_api_key in {path.root}.")
    client = LinearClient(api_key=key.root)
    workspace = Workspace.of(client).organization.url_key
    if workspace != WorkspaceKey("mb-workflow-integration-test"):
        pytest.fail(f"The API key belongs to {workspace.root}, not the integration-test workspace.")
    return client


def ensure_labels(client: LinearClient, wanted: LabelNames) -> None:
    existing = LabelNames(
        tuple(
            LabelName(label.name)
            for label in client.paginate(client.issue_labels, IssueLabelsRequest(first=250))
            if label.name
        )
    )
    for label in existing.unmatched(wanted).root:
        _ = client.execute(
            "mutation($name: String!) { issueLabelCreate(input: { name: $name }) { success } }",
            {"name": label.root},
        )


class HeldProject(Payload):
    milestones: tuple[MilestonePayload, ...] = Field(
        default=(), validation_alias=AliasPath("project", "projectMilestones", "nodes")
    )

    @staticmethod
    def fake() -> HeldProject:
        return HeldProject(milestones=(MilestonePayload.fake(),))

    def names(self) -> MilestoneNames:
        return MilestoneNames(tuple(milestone.name for milestone in self.milestones))


def find_project(client: LinearClient, project: ProjectName) -> ProjectId | None:
    found = client.find_project(FindProjectRequest(name=project.root)).project
    return ProjectId(found.id) if found is not None and found.id is not None else None


def ensure_project(client: LinearClient, team: TeamId, project: Project) -> ProjectId:
    if find_project(client, project.name) is None:
        _ = client.execute(
            "mutation($name: String!, $team: String!) {"
            " projectCreate(input: { name: $name, teamIds: [$team] }) { success } }",
            {"name": project.name.root, "team": team.root},
        )
    created = find_project(client, project.name)
    if created is None:
        pytest.fail(f"Linear did not create {project.name.root}.")
    held = HeldProject.model_validate(
        client.execute(
            "query($id: String!) { project(id: $id) { projectMilestones { nodes { name } } } }",
            {"id": created.root},
        )
    ).names()
    for milestone in project.milestones.root:
        if held.matching(milestone) is None:
            _ = client.execute(
                "mutation($name: String!, $project: String!) {"
                " projectMilestoneCreate(input: { name: $name, projectId: $project })"
                " { success } }",
                {"name": milestone.root, "project": created.root},
            )
    return created


def ensure_issue(client: LinearClient, team: TeamId, planted: SeededIssue) -> IssueIdentifier:
    title = planted.title().root
    found = client.issues(IssuesRequest(filter={"title": {"eq": title}})).nodes
    if found and found[0].identifier:
        return IssueIdentifier(found[0].identifier)
    created = client.create_issue(
        IssueCreateRequest(
            team_id=team.root,
            title=title,
            state_id=planted.status.root,
            project_id=planted.project.root if planted.project is not None else None,
            priority=planted.priority.value,
            createdAt=f"{planted.created_on.root.isoformat()}T12:00:00Z",
        )
    ).issue
    if created is None or created.identifier is None:
        pytest.fail(f"Linear did not create {title}.")
    return IssueIdentifier(created.identifier)


class ViewRecord(Payload):
    slug_id: ViewSlug

    @staticmethod
    def fake() -> ViewRecord:
        return ViewRecord(slug_id=ViewSlug.fake())


class FoundViews(Payload):
    views: tuple[ViewRecord, ...] = Field(validation_alias=AliasPath("customViews", "nodes"))

    @staticmethod
    def fake() -> FoundViews:
        return FoundViews(views=(ViewRecord.fake(),))


class CreatedView(Payload):
    view: ViewRecord = Field(validation_alias=AliasPath("customViewCreate", "customView"))

    @staticmethod
    def fake() -> CreatedView:
        return CreatedView(view=ViewRecord.fake())


class RelatedIssue(Payload):
    identifier: IssueIdentifier

    @staticmethod
    def fake() -> RelatedIssue:
        return RelatedIssue(identifier=IssueIdentifier.fake())


class RelationKind(StrEnum):
    blocks = "blocks"
    related = "related"


class HeldRelation(Payload):
    type: RelationKind
    related_issue: RelatedIssue

    @staticmethod
    def fake() -> HeldRelation:
        return HeldRelation(type=RelationKind.blocks, related_issue=RelatedIssue.fake())


class HeldRelations(Payload):
    relations: tuple[HeldRelation, ...] = Field(
        validation_alias=AliasPath("issue", "relations", "nodes")
    )

    @staticmethod
    def fake() -> HeldRelations:
        return HeldRelations(relations=(HeldRelation.fake(),))


def ensure_relation(
    client: LinearClient, issue: IssueIdentifier, related: IssueIdentifier, kind: RelationKind
) -> None:
    held = HeldRelations.model_validate(
        client.execute(
            "query($id: String!) {"
            " issue(id: $id) { relations { nodes { type relatedIssue { identifier } } } } }",
            {"id": issue.root},
        )
    )
    if HeldRelation(type=kind, related_issue=RelatedIssue(identifier=related)) in held.relations:
        return
    _ = client.execute(
        "mutation($input: IssueRelationCreateInput!) {"
        " issueRelationCreate(input: $input) { success } }",
        {"input": {"issueId": issue.root, "relatedIssueId": related.root, "type": kind.value}},
    )


# The view filters on the seeds' shared title prefix, so it holds every seed and nothing else.
def ensure_view(client: LinearClient) -> ViewSlug:
    name = "contract: pool"
    found = FoundViews.model_validate(
        client.execute(
            "query($name: String!) {"
            " customViews(first: 1, filter: { name: { eq: $name } }) { nodes { slugId } } }",
            {"name": name},
        )
    ).views
    if found:
        return found[0].slug_id
    return CreatedView.model_validate(
        client.execute(
            "mutation($input: CustomViewCreateInput!) {"
            " customViewCreate(input: $input) { customView { slugId } } }",
            {
                "input": {
                    "name": name,
                    "shared": True,
                    "filterData": {"title": {"startsWith": "contract: "}},
                }
            },
        )
    ).view.slug_id


# Seeded once per session; reset() restores whatever a test changes.
@pytest.fixture(scope="session")
def linear_backlog(linear_client: LinearClient) -> Backlog:
    other = Workspace.ensure_other_team(linear_client)
    team = next(team for team in Workspace.of(linear_client).teams if team.key != other.key)
    ensure_labels(linear_client, workspace_labels())
    _ = ensure_project(linear_client, team.id, Project.fake())
    viewer = linear_client.viewer().viewer
    if viewer is None or viewer.email is None:
        pytest.fail("Linear did not say who the API key belongs to.")
    backlog = Backlog(
        identifiers={
            planted.seed: ensure_issue(linear_client, team.id, planted) for planted in seeds()
        },
        creator=Creator(viewer.email),
        assignee=Assignee(viewer.email),
        view=ensure_view(linear_client),
        team=team.key,
        team_name=team.name,
        other_team=other.key,
        other_team_name=other.name,
    )
    for planted in seeds():
        for blocker in planted.blocked_by:
            ensure_relation(
                linear_client,
                backlog.identifier(blocker),
                backlog.identifier(planted.seed),
                RelationKind.blocks,
            )
    # Only a blocking relation holds a ticket back, so the suite also seeds one that doesn't.
    ensure_relation(
        linear_client,
        backlog.identifier(Seed.newest),
        backlog.identifier(Seed.done),
        RelationKind.related,
    )
    return backlog


def reset(client: LinearClient, backlog: Backlog) -> None:
    tracker = Linear(client)
    claims = LinearClaims(client)
    for planted in seeds():
        identifier = backlog.identifier(planted.seed)
        for stale in claims.claims(identifier).unwrap().root:
            claims.withdraw(identifier, stale.id).unwrap()
        tracker.set_labels(identifier, planted.labels).unwrap()
        tracker.update_issue(
            identifier, IssueUpdate.nothing().model_copy(update={"status": planted.status})
        ).unwrap()
        project = find_project(client, planted.project) if planted.project else None
        _ = client.execute(
            "mutation($id: String!, $input: IssueUpdateInput!) {"
            " issueUpdate(id: $id, input: $input) { success } }",
            {
                "id": identifier.root,
                "input": {
                    "title": planted.title().root,
                    "description": planted.description.root if planted.description else None,
                    "assigneeId": None,
                    "projectId": project.root if project is not None else None,
                    "projectMilestoneId": None,
                    "priority": planted.priority.value,
                },
            },
        )


@pytest.fixture(
    params=[TrackerKind.fake, pytest.param(TrackerKind.linear, marks=pytest.mark.linear_live)]
)
def kind(request: pytest.FixtureRequest) -> TrackerKind:
    return TrackerKind(request.param)


@pytest.fixture
def backlog(kind: TrackerKind, request: pytest.FixtureRequest) -> Backlog:
    if kind == TrackerKind.fake:
        return fake_backlog()
    client: LinearClient = request.getfixturevalue("linear_client")
    planted: Backlog = request.getfixturevalue("linear_backlog")
    reset(client, planted)
    return planted


@pytest.fixture
def tracker(kind: TrackerKind, backlog: Backlog, request: pytest.FixtureRequest) -> TicketTracker:
    if kind == TrackerKind.linear:
        return Linear(request.getfixturevalue("linear_client"))
    return FakeTicketTracker(
        workspace_labels(),
        tuple(
            TrackedIssue(
                issue=planted.issue(backlog.identifier(planted.seed)),
                title=planted.title(),
                description=planted.description,
                assignee=None,
                milestone=None,
                creator=backlog.creator,
                created_on=planted.created_on,
                priority=planted.priority,
                blocked_by=tuple(backlog.identifier(blocker) for blocker in planted.blocked_by),
                team=backlog.team,
            )
            for planted in seeds()
        ),
        Projects.fake(),
        IssueStatuses(
            (
                *IssueStatuses.fake().root,
                IssueStatus(name=IssueStatusName("Canceled"), type=StatusType.canceled),
                IssueStatus(name=IssueStatusName("Duplicate"), type=StatusType.canceled),
            )
        ),
        backlog.assignee,
        views={backlog.view: tuple(backlog.identifier(seed) for seed in Seed)},
        teams=(
            Team(key=backlog.team, name=backlog.team_name, projects=(ProjectName.fake(),)),
            Team(key=backlog.other_team, name=backlog.other_team_name, projects=()),
        ),
    )


def drop_group(client: LinearClient, group: LabelGroupName) -> None:
    found = LabelGroupRead.model_validate(
        client.execute(
            "query($name: String!) { issueLabels(first: 250, filter:"
            " { name: { eqIgnoreCase: $name }, isGroup: { eq: true } })"
            " { nodes { id children(first: 250) { nodes { id name color } } } } }",
            {"name": group.root},
        )
    ).groups
    for held in found:
        for label in (*(child.id for child in held.children), held.id):
            _ = client.execute(
                "mutation($id: String!) { issueLabelDelete(id: $id) { success } }",
                {"id": label.root},
            )


# Linear keeps a created group between runs, so each test that seeds one starts without it.
@pytest.fixture
def groupless(
    kind: TrackerKind, tracker: TicketTracker, request: pytest.FixtureRequest
) -> TicketTracker:
    if kind == TrackerKind.linear:
        drop_group(request.getfixturevalue("linear_client"), LabelGroupName.fake())
    return tracker


@pytest.fixture
def claims(kind: TrackerKind, request: pytest.FixtureRequest) -> ClaimRegistry:
    if kind == TrackerKind.linear:
        return LinearClaims(request.getfixturevalue("linear_client"))
    return FakeClaimRegistry()


def test_every_workspace_label_is_listed(tracker: TicketTracker) -> None:
    assert tracker.workspace_labels().unwrap().unmatched(workspace_labels()) == LabelNames(())


GRILL = LabelName("grill")
QA = LabelName("qa")


def test_a_created_group_lists_its_labels_back(groupless: TicketTracker) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((GRILL, QA))), None
    ).unwrap()
    assert set(
        groupless.group_labels(LabelGroupName.fake(), None).unwrap().label_names().root
    ) == set(LabelNames((GRILL, QA)).root)


def test_labels_added_to_a_group_join_the_ones_there(groupless: TicketTracker) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((GRILL,))), None
    ).unwrap()
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((QA,))), None
    ).unwrap()
    assert set(
        groupless.group_labels(LabelGroupName.fake(), None).unwrap().label_names().root
    ) == set(LabelNames((GRILL, QA)).root)


def test_a_created_group_reads_back_the_colors_of_its_labels(
    groupless: TicketTracker, backlog: Backlog
) -> None:
    created = FlowLabels.fake().colored(LabelNames((GRILL, QA)))
    groupless.create_group_labels(LabelGroupName.fake(), created, backlog.team).unwrap()
    assert set(groupless.group_labels(LabelGroupName.fake(), backlog.team).unwrap().root) == set(
        created.root
    )


def test_a_recolored_label_reads_back_its_new_color(
    groupless: TicketTracker, backlog: Backlog
) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((QA,))), backlog.team
    ).unwrap()
    yellow = ColoredLabels((ColoredLabel(name=QA, color=LabelColor.yellow()),))
    groupless.recolor_group_labels(LabelGroupName.fake(), yellow, backlog.team).unwrap()
    assert groupless.group_labels(LabelGroupName.fake(), backlog.team).unwrap() == yellow


def test_recoloring_a_label_the_group_lacks_is_refused(
    groupless: TicketTracker, backlog: Backlog
) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((QA,))), backlog.team
    ).unwrap()
    yellow = ColoredLabels((ColoredLabel(name=GRILL, color=LabelColor.yellow()),))
    refused = groupless.recolor_group_labels(LabelGroupName.fake(), yellow, backlog.team)
    assert isinstance(refused, Err)
    assert GRILL.root in str(refused.error)


def test_a_renamed_label_reads_back_its_new_name(
    groupless: TicketTracker, backlog: Backlog
) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((QA,))), backlog.team
    ).unwrap()
    renamed = LabelName("qa")
    groupless.rename_group_label(LabelGroupName.fake(), QA, renamed, backlog.team).unwrap()
    assert groupless.group_labels(
        LabelGroupName.fake(), backlog.team
    ).unwrap().label_names() == LabelNames((renamed,))


def test_a_renamed_label_stays_on_its_tickets(groupless: TicketTracker, backlog: Backlog) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((QA,))), None
    ).unwrap()
    groupless.add_label(backlog.identifier(Seed.done), QA).unwrap()
    renamed = LabelName("qa")
    groupless.rename_group_label(LabelGroupName.fake(), QA, renamed, None).unwrap()
    assert renamed in groupless.read_issue(backlog.identifier(Seed.done)).unwrap().labels.root


def test_a_renamed_team_label_stays_on_the_teams_tickets(
    groupless: TicketTracker, backlog: Backlog
) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((QA,))), backlog.team
    ).unwrap()
    groupless.add_label(backlog.identifier(Seed.done), QA).unwrap()
    renamed = LabelName("qa")
    groupless.rename_group_label(LabelGroupName.fake(), QA, renamed, backlog.team).unwrap()
    assert renamed in groupless.read_issue(backlog.identifier(Seed.done)).unwrap().labels.root


def test_a_deleted_team_label_leaves_the_teams_tickets(
    groupless: TicketTracker, backlog: Backlog
) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((QA,))), backlog.team
    ).unwrap()
    groupless.add_label(backlog.identifier(Seed.done), QA).unwrap()
    groupless.delete_group_label(LabelGroupName.fake(), QA, backlog.team).unwrap()
    held = groupless.read_issue(backlog.identifier(Seed.done)).unwrap().labels
    assert held.matching(QA) is None


def test_renaming_a_label_the_group_lacks_is_refused(
    groupless: TicketTracker, backlog: Backlog
) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((QA,))), backlog.team
    ).unwrap()
    refused = groupless.rename_group_label(
        LabelGroupName.fake(), GRILL, LabelName("grilling"), backlog.team
    )
    assert isinstance(refused, Err)
    assert GRILL.root in str(refused.error)


def test_a_deleted_label_leaves_its_group(groupless: TicketTracker, backlog: Backlog) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((GRILL, QA))), backlog.team
    ).unwrap()
    groupless.delete_group_label(LabelGroupName.fake(), QA, backlog.team).unwrap()
    assert groupless.group_labels(
        LabelGroupName.fake(), backlog.team
    ).unwrap().label_names() == LabelNames((GRILL,))


def test_a_deleted_label_leaves_its_tickets(groupless: TicketTracker, backlog: Backlog) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((QA,))), None
    ).unwrap()
    groupless.add_label(backlog.identifier(Seed.done), QA).unwrap()
    groupless.delete_group_label(LabelGroupName.fake(), QA, None).unwrap()
    held = groupless.read_issue(backlog.identifier(Seed.done)).unwrap().labels
    assert held.matching(QA) is None


def test_deleting_a_label_the_group_lacks_is_refused(
    groupless: TicketTracker, backlog: Backlog
) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((QA,))), backlog.team
    ).unwrap()
    refused = groupless.delete_group_label(LabelGroupName.fake(), GRILL, backlog.team)
    assert isinstance(refused, Err)
    assert GRILL.root in str(refused.error)


def test_a_group_label_counts_the_tickets_carrying_it(
    groupless: TicketTracker, backlog: Backlog
) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((GRILL, QA))), None
    ).unwrap()
    carrying = (Seed.done, Seed.recent)
    for seed in carrying:
        groupless.add_label(backlog.identifier(seed), QA).unwrap()
    assert groupless.labelled_ticket_count(LabelGroupName.fake(), QA, None).unwrap() == (
        TicketCount(len(carrying))
    )


def test_a_group_label_no_ticket_carries_counts_none(
    groupless: TicketTracker, backlog: Backlog
) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((QA,))), backlog.team
    ).unwrap()
    assert groupless.labelled_ticket_count(
        LabelGroupName.fake(), QA, backlog.team
    ).unwrap() == TicketCount(0)


def test_a_group_that_does_not_exist_lists_no_labels(groupless: TicketTracker) -> None:
    assert groupless.group_labels(LabelGroupName.fake(), None).unwrap() == ColoredLabels(())


def test_a_group_created_in_a_team_lists_its_labels_under_the_team(
    groupless: TicketTracker, backlog: Backlog
) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((GRILL, QA))), backlog.team
    ).unwrap()
    assert set(
        groupless.group_labels(LabelGroupName.fake(), backlog.team).unwrap().label_names().root
    ) == set(LabelNames((GRILL, QA)).root)


def test_a_group_created_in_a_team_is_not_a_workspace_group(
    groupless: TicketTracker, backlog: Backlog
) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((GRILL, QA))), backlog.team
    ).unwrap()
    assert groupless.group_labels(LabelGroupName.fake(), None).unwrap() == ColoredLabels(())


def test_a_group_created_in_a_team_is_not_listed_under_another_team(
    groupless: TicketTracker, backlog: Backlog
) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((GRILL, QA))), backlog.team
    ).unwrap()
    assert groupless.group_labels(
        LabelGroupName.fake(), backlog.other_team
    ).unwrap() == ColoredLabels(())


def test_a_workspace_group_is_not_listed_under_a_team(
    groupless: TicketTracker, backlog: Backlog
) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((GRILL, QA))), None
    ).unwrap()
    assert groupless.group_labels(LabelGroupName.fake(), backlog.team).unwrap() == ColoredLabels(())


def test_a_team_is_found_by_its_name(tracker: TicketTracker, backlog: Backlog) -> None:
    assert tracker.team_named(backlog.team_name).unwrap() == backlog.team


def test_a_team_is_found_by_its_name_whatever_its_case(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    assert tracker.team_named(TeamName(backlog.team_name.root.upper())).unwrap() == backlog.team


def test_an_unknown_team_name_is_refused(tracker: TicketTracker) -> None:
    unknown = TeamName("No such team")
    refused = tracker.team_named(unknown)
    assert isinstance(refused, Err)
    assert unknown.root in str(refused.error)


def test_an_issue_names_its_team(tracker: TicketTracker, backlog: Backlog) -> None:
    assert tracker.team_of(backlog.identifier(Seed.done)).unwrap() == backlog.team


def test_the_team_of_an_unknown_issue_is_refused(tracker: TicketTracker) -> None:
    assert isinstance(tracker.team_of(IssueIdentifier("E-404")), Err)


def test_an_issue_takes_its_own_teams_label_over_a_namesake_in_another_team(
    groupless: TicketTracker, backlog: Backlog
) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((QA,))), backlog.other_team
    ).unwrap()
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((QA,))), backlog.team
    ).unwrap()
    groupless.update_issue(
        backlog.identifier(Seed.done),
        IssueUpdate.nothing().model_copy(update={"labels": LabelNames((QA,))}),
    ).unwrap()
    assert groupless.read_issue(backlog.identifier(Seed.done)).unwrap().labels == LabelNames((QA,))


def test_setting_labels_takes_the_issues_own_teams_label_over_a_namesake(
    groupless: TicketTracker, backlog: Backlog
) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((QA,))), backlog.other_team
    ).unwrap()
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((QA,))), backlog.team
    ).unwrap()
    groupless.set_labels(backlog.identifier(Seed.done), LabelNames((QA,))).unwrap()
    assert groupless.read_issue(backlog.identifier(Seed.done)).unwrap().labels == LabelNames((QA,))


def test_adding_a_label_cannot_take_another_teams_label(
    groupless: TicketTracker, backlog: Backlog
) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((QA,))), backlog.other_team
    ).unwrap()
    refused = groupless.add_label(backlog.identifier(Seed.done), QA)
    assert isinstance(refused, Err)
    assert QA.root in str(refused.error)


def test_an_issue_takes_a_workspace_label_its_team_lacks(
    groupless: TicketTracker, backlog: Backlog
) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((QA,))), None
    ).unwrap()
    groupless.update_issue(
        backlog.identifier(Seed.done),
        IssueUpdate.nothing().model_copy(update={"labels": LabelNames((QA,))}),
    ).unwrap()
    assert groupless.read_issue(backlog.identifier(Seed.done)).unwrap().labels == LabelNames((QA,))


def test_an_issue_cannot_take_another_teams_label(
    groupless: TicketTracker, backlog: Backlog
) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((QA,))), backlog.other_team
    ).unwrap()
    refused = groupless.update_issue(
        backlog.identifier(Seed.done),
        IssueUpdate.nothing().model_copy(update={"labels": LabelNames((QA,))}),
    )
    assert isinstance(refused, Err)
    assert QA.root in str(refused.error)


def test_a_grouped_label_names_its_group(groupless: TicketTracker) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((GRILL, QA))), None
    ).unwrap()
    assert groupless.label_group(QA).unwrap() == LabelGroupName.fake()


def test_an_ungrouped_label_names_no_group(tracker: TicketTracker) -> None:
    assert tracker.label_group(LabelName("d-grill")).unwrap() is None


def test_an_issue_carries_a_label_of_a_group(groupless: TicketTracker, backlog: Backlog) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((GRILL, QA))), None
    ).unwrap()
    groupless.set_labels(
        backlog.identifier(Seed.done), LabelNames((LabelName("d-grill"), QA))
    ).unwrap()
    assert set(groupless.read_issue(backlog.identifier(Seed.done)).unwrap().labels.root) == set(
        LabelNames((LabelName("d-grill"), QA)).root
    )


def test_an_issue_reads_back_the_group_of_its_labels(
    groupless: TicketTracker, backlog: Backlog
) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((GRILL, QA))), None
    ).unwrap()
    groupless.set_labels(
        backlog.identifier(Seed.done), LabelNames((LabelName("d-grill"), QA))
    ).unwrap()
    assert groupless.read_issue(backlog.identifier(Seed.done)).unwrap().grouped.in_group(
        LabelGroupName.fake()
    ) == LabelNames((QA,))


def test_an_issue_carrying_two_labels_of_one_group_is_refused(
    groupless: TicketTracker, backlog: Backlog
) -> None:
    groupless.create_group_labels(
        LabelGroupName.fake(), FlowLabels.fake().colored(LabelNames((GRILL, QA))), None
    ).unwrap()
    refused = groupless.set_labels(backlog.identifier(Seed.done), LabelNames((GRILL, QA)))
    assert isinstance(refused, Err)


def test_the_filter_picks_the_issues_one_creator_made_since_a_date(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    since = IssueFilter(creator=backlog.creator, created_after=CreatedAfter(date(2026, 8, 9)))
    assert backlog.picked(since, tracker) == (Seed.recent, Seed.newest, Seed.done)


def test_the_filter_skips_issues_another_creator_made(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    other = IssueFilter(
        creator=Creator("someone@flowbase.io"), created_after=CreatedAfter(date(2026, 8, 9))
    )
    assert backlog.picked(other, tracker) == ()


def test_the_filter_start_date_is_inclusive(tracker: TicketTracker, backlog: Backlog) -> None:
    after = IssueFilter(creator=backlog.creator, created_after=CreatedAfter(date(2026, 9, 2)))
    assert backlog.picked(after, tracker) == (Seed.newest,)


def listed(tracker: TicketTracker, backlog: Backlog) -> set[Seed]:
    shown = tracker.unblocked_view_tickets(backlog.view).unwrap().identifiers()
    return {seed for seed in Seed if backlog.identifier(seed) in shown}


def test_a_view_lists_its_unblocked_tickets_with_their_priority(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    assert set(tracker.unblocked_view_tickets(backlog.view).unwrap().root) == {
        backlog.ticket(seed) for seed in set(Seed) - {Seed.recent}
    }


def test_a_ticket_with_one_open_blocker_among_closed_ones_is_left_out_of_a_view(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    assert Seed.recent not in listed(tracker, backlog)


@pytest.mark.parametrize("status", ["Done", "Canceled"])
def test_a_ticket_whose_blockers_are_all_closed_is_listed(
    tracker: TicketTracker, backlog: Backlog, status: str
) -> None:
    tracker.update_issue(
        backlog.identifier(Seed.old),
        IssueUpdate.nothing().model_copy(update={"status": IssueStatusName(status)}),
    ).unwrap()
    assert Seed.recent in listed(tracker, backlog)


def test_reading_an_unknown_view_is_refused(tracker: TicketTracker) -> None:
    assert isinstance(tracker.unblocked_view_tickets(ViewSlug("000000000000")), Err)


def labelled_seeds(
    tracker: TicketTracker, backlog: Backlog, label: LabelName, excluding: StatusTypes
) -> set[Seed]:
    listed = tracker.labelled_issues(label, excluding).unwrap().identifiers()
    return {seed for seed in Seed if backlog.identifier(seed) in listed}


def test_the_issues_carrying_a_label_are_listed(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.add_label(backlog.identifier(Seed.recent), LabelName("d-grill")).unwrap()
    assert labelled_seeds(tracker, backlog, LabelName("d-grill"), StatusTypes(())) == {
        Seed.recent,
        Seed.done,
    }


def test_labelled_issues_of_an_excluded_status_type_are_left_out(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    for seed in (Seed.recent, Seed.old):
        tracker.add_label(backlog.identifier(seed), LabelName("d-grill")).unwrap()
    tracker.update_issue(
        backlog.identifier(Seed.old),
        IssueUpdate.nothing().model_copy(update={"status": IssueStatusName("Canceled")}),
    ).unwrap()
    excluding = StatusTypes((StatusType.completed, StatusType.canceled))
    assert labelled_seeds(tracker, backlog, LabelName("d-grill"), excluding) == {Seed.recent}


def test_a_labelled_issue_is_found_whatever_the_label_case(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    assert labelled_seeds(tracker, backlog, LabelName("D-Grill"), StatusTypes(())) == {Seed.done}


def test_reads_an_issue_back_as_it_was_given(tracker: TicketTracker, backlog: Backlog) -> None:
    assert tracker.read_issue(backlog.identifier(Seed.done)).unwrap() == backlog.issue(Seed.done)


def test_an_issue_without_a_project_carries_none(tracker: TicketTracker, backlog: Backlog) -> None:
    assert tracker.read_issue(backlog.identifier(Seed.done)).unwrap().project is None


def test_a_project_survives_the_round_trip(tracker: TicketTracker, backlog: Backlog) -> None:
    assert (
        tracker.read_issue(backlog.identifier(Seed.recent)).unwrap().project == ProjectName.fake()
    )


def test_reading_an_unknown_issue_is_refused(tracker: TicketTracker) -> None:
    assert isinstance(tracker.read_issue(IssueIdentifier("E-404")), Err)


def test_viewing_an_issue_carries_its_title_and_description(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    assert tracker.read_issue_detail(backlog.identifier(Seed.recent)).unwrap() == backlog.detail(
        Seed.recent
    )


def test_viewing_an_issue_carries_the_issues_it_blocks(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    assert tracker.read_issue_detail(backlog.identifier(Seed.old)).unwrap().blocks == frozenset(
        {backlog.identifier(Seed.recent)}
    )


def test_viewing_an_issue_leaves_out_relations_that_do_not_block(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    detail = tracker.read_issue_detail(backlog.identifier(Seed.newest)).unwrap()
    assert (detail.blocks, detail.blocked_by) == (frozenset(), frozenset())


def test_an_issue_without_a_description_carries_none(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    assert tracker.read_issue_detail(backlog.identifier(Seed.done)).unwrap().description is None


def test_viewing_an_unknown_issue_is_refused(tracker: TicketTracker) -> None:
    assert isinstance(tracker.read_issue_detail(IssueIdentifier("E-404")), Err)


def test_the_blockers_of_an_unknown_issue_are_refused(tracker: TicketTracker) -> None:
    assert isinstance(tracker.blockers(IssueIdentifier("E-404")), Err)


def test_an_added_label_joins_the_ones_already_there(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    tracker.add_label(backlog.identifier(Seed.done), LabelName.fake()).unwrap()
    assert set(tracker.read_issue(backlog.identifier(Seed.done)).unwrap().labels.root) == {
        LabelName("d-grill"),
        LabelName.fake(),
    }


def test_adding_a_label_twice_carries_it_once(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.add_label(backlog.identifier(Seed.recent), LabelName.fake()).unwrap()
    tracker.add_label(backlog.identifier(Seed.recent), LabelName.fake()).unwrap()
    assert tracker.read_issue(backlog.identifier(Seed.recent)).unwrap().labels == LabelNames.fake()


def test_adding_an_unknown_label_is_refused(tracker: TicketTracker, backlog: Backlog) -> None:
    refused = tracker.add_label(backlog.identifier(Seed.recent), LabelName("Frontend"))
    assert isinstance(refused, Err)


def test_a_removed_label_leaves_the_others(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.add_label(backlog.identifier(Seed.done), LabelName.fake()).unwrap()
    tracker.remove_label(backlog.identifier(Seed.done), LabelName("d-grill")).unwrap()
    assert tracker.read_issue(backlog.identifier(Seed.done)).unwrap().labels == LabelNames(
        (LabelName.fake(),)
    )


def test_removing_a_label_the_issue_lacks_leaves_it_unchanged(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    tracker.remove_label(backlog.identifier(Seed.done), LabelName.fake()).unwrap()
    assert tracker.read_issue(backlog.identifier(Seed.done)).unwrap().labels == LabelNames(
        (LabelName("d-grill"),)
    )


def test_setting_labels_replaces_the_ones_there(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.set_labels(backlog.identifier(Seed.done), LabelNames((LabelName("Backend"),))).unwrap()
    assert tracker.read_issue(backlog.identifier(Seed.done)).unwrap().labels == LabelNames(
        (LabelName("Backend"),)
    )


def test_setting_no_labels_clears_them(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.set_labels(backlog.identifier(Seed.done), LabelNames(())).unwrap()
    assert tracker.read_issue(backlog.identifier(Seed.done)).unwrap().labels == LabelNames(())


def test_setting_an_unknown_label_is_refused(tracker: TicketTracker, backlog: Backlog) -> None:
    refused = tracker.set_labels(
        backlog.identifier(Seed.done), LabelNames((LabelName("Frontend"),))
    )
    assert isinstance(refused, Err)


def test_an_issue_starts_unassigned(tracker: TicketTracker, backlog: Backlog) -> None:
    assert tracker.read_issue(backlog.identifier(Seed.recent)).unwrap().assigned == Assigned(False)


def test_assigning_an_issue_leaves_it_assigned(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.assign(backlog.identifier(Seed.recent), backlog.assignee).unwrap()
    assert tracker.read_issue(backlog.identifier(Seed.recent)).unwrap().assigned == Assigned(True)


def test_assigning_an_unknown_issue_is_refused(tracker: TicketTracker, backlog: Backlog) -> None:
    refused = tracker.assign(IssueIdentifier("E-404"), backlog.assignee)
    assert isinstance(refused, Err)


def test_a_label_is_found_whatever_its_case(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.add_label(backlog.identifier(Seed.recent), LabelName("D-IMPLEMENT")).unwrap()
    assert tracker.read_issue(backlog.identifier(Seed.recent)).unwrap().labels == LabelNames.fake()


def test_setting_labels_takes_the_workspace_spelling(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    tracker.set_labels(
        backlog.identifier(Seed.recent), LabelNames((LabelName("backend"),))
    ).unwrap()
    assert tracker.read_issue(backlog.identifier(Seed.recent)).unwrap().labels == LabelNames(
        (LabelName("Backend"),)
    )


def test_adding_a_label_in_another_case_carries_it_once(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    tracker.add_label(backlog.identifier(Seed.recent), LabelName.fake()).unwrap()
    tracker.add_label(backlog.identifier(Seed.recent), LabelName("D-Implement")).unwrap()
    assert tracker.read_issue(backlog.identifier(Seed.recent)).unwrap().labels == LabelNames.fake()


def test_the_viewer_is_the_one_holding_the_key(tracker: TicketTracker, backlog: Backlog) -> None:
    assert tracker.viewer().unwrap() == backlog.assignee


def test_an_update_sets_the_title_and_description(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.update_issue(
        backlog.identifier(Seed.done),
        IssueUpdate.nothing().model_copy(
            update={
                "title": IssueTitle("contract: renamed"),
                "description": IssueDescription("Rewritten."),
            }
        ),
    ).unwrap()
    detail = tracker.read_issue_detail(backlog.identifier(Seed.done)).unwrap()
    assert (detail.title, detail.description) == (
        IssueTitle("contract: renamed"),
        IssueDescription("Rewritten."),
    )


def test_an_update_leaves_the_fields_it_does_not_name(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    tracker.update_issue(
        backlog.identifier(Seed.done),
        IssueUpdate.nothing().model_copy(update={"title": IssueTitle("contract: x")}),
    ).unwrap()
    assert tracker.read_issue(backlog.identifier(Seed.done)).unwrap() == backlog.issue(Seed.done)


def test_an_update_replaces_the_labels(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.update_issue(
        backlog.identifier(Seed.done),
        IssueUpdate.nothing().model_copy(update={"labels": LabelNames((LabelName("backend"),))}),
    ).unwrap()
    assert tracker.read_issue(backlog.identifier(Seed.done)).unwrap().labels == LabelNames(
        (LabelName("Backend"),)
    )


def test_an_update_with_an_unknown_label_is_refused(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    refused = tracker.update_issue(
        backlog.identifier(Seed.done),
        IssueUpdate.nothing().model_copy(update={"labels": LabelNames((LabelName("Frontend"),))}),
    )
    assert isinstance(refused, Err)


def test_an_update_names_the_assignee(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.update_issue(
        backlog.identifier(Seed.recent),
        IssueUpdate.nothing().model_copy(update={"assignee": backlog.assignee}),
    ).unwrap()
    detail = tracker.read_issue_detail(backlog.identifier(Seed.recent)).unwrap()
    assert (detail.assignee, detail.issue.assigned) == (backlog.assignee, Assigned(True))


def test_an_update_can_unassign(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.update_issue(
        backlog.identifier(Seed.recent),
        IssueUpdate.nothing().model_copy(update={"assignee": backlog.assignee}),
    ).unwrap()
    tracker.update_issue(
        backlog.identifier(Seed.recent),
        IssueUpdate.nothing().model_copy(update={"assignee": Cleared()}),
    ).unwrap()
    detail = tracker.read_issue_detail(backlog.identifier(Seed.recent)).unwrap()
    assert (detail.assignee, detail.issue.assigned) == (None, Assigned(False))


def test_an_update_moves_an_issue_into_a_project(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.update_issue(
        backlog.identifier(Seed.done),
        IssueUpdate.nothing().model_copy(update={"project": ProjectName.fake()}),
    ).unwrap()
    assert tracker.read_issue(backlog.identifier(Seed.done)).unwrap().project == ProjectName.fake()


def test_an_update_can_take_an_issue_out_of_its_project(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    tracker.update_issue(
        backlog.identifier(Seed.recent),
        IssueUpdate.nothing().model_copy(update={"project": Cleared()}),
    ).unwrap()
    assert tracker.read_issue(backlog.identifier(Seed.recent)).unwrap().project is None


def test_moving_to_an_unknown_project_is_refused(tracker: TicketTracker, backlog: Backlog) -> None:
    refused = tracker.update_issue(
        backlog.identifier(Seed.recent),
        IssueUpdate.nothing().model_copy(update={"project": ProjectName("No such project")}),
    )
    assert isinstance(refused, Err)


def test_an_update_sets_a_milestone(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.update_issue(
        backlog.identifier(Seed.recent),
        IssueUpdate.nothing().model_copy(update={"milestone": Milestone.fake()}),
    ).unwrap()
    assert tracker.read_issue_detail(backlog.identifier(Seed.recent)).unwrap().milestone == (
        MilestoneName.fake()
    )


def test_an_update_can_clear_the_milestone(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.update_issue(
        backlog.identifier(Seed.recent),
        IssueUpdate.nothing().model_copy(update={"milestone": Milestone.fake()}),
    ).unwrap()
    tracker.update_issue(
        backlog.identifier(Seed.recent),
        IssueUpdate.nothing().model_copy(update={"milestone": Cleared()}),
    ).unwrap()
    assert tracker.read_issue_detail(backlog.identifier(Seed.recent)).unwrap().milestone is None


def test_an_unknown_milestone_is_refused(tracker: TicketTracker, backlog: Backlog) -> None:
    unknown = Milestone(project=ProjectName.fake(), name=MilestoneName("No such milestone"))
    refused = tracker.update_issue(
        backlog.identifier(Seed.recent),
        IssueUpdate.nothing().model_copy(update={"milestone": unknown}),
    )
    assert isinstance(refused, Err)


def test_an_update_moves_an_issue_to_a_status(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.update_issue(
        backlog.identifier(Seed.recent),
        IssueUpdate.nothing().model_copy(update={"status": IssueStatusName("in progress")}),
    ).unwrap()
    assert tracker.read_issue(backlog.identifier(Seed.recent)).unwrap().status == IssueStatusName(
        "In Progress"
    )


def test_moving_to_an_unknown_status_is_refused(tracker: TicketTracker, backlog: Backlog) -> None:
    refused = tracker.update_issue(
        backlog.identifier(Seed.recent),
        IssueUpdate.nothing().model_copy(update={"status": IssueStatusName("No such status")}),
    )
    assert isinstance(refused, Err)


# Created issues go to the trash afterwards, so they never join the seeds' labels or view.
@pytest.fixture
def creating(
    kind: TrackerKind, tracker: TicketTracker, request: pytest.FixtureRequest
) -> Generator[Creating]:
    made: list[IssueIdentifier] = []

    def create(new: NewIssue) -> Result[CreatedIssue, TicketTrackerError]:
        created = tracker.create_issue(new)
        if isinstance(created, Ok):
            made.append(created.value.identifier)
        return created

    yield create
    if kind == TrackerKind.linear:
        client: LinearClient = request.getfixturevalue("linear_client")
        for identifier in made:
            _ = client.execute(
                "mutation($id: String!) { issueDelete(id: $id) { success } }",
                {"id": identifier.root},
            )


def new_issue(title: IssueTitle) -> NewIssue:
    return NewIssue(
        team=None,
        title=title,
        description=None,
        labels=LabelNames(()),
        assignee=None,
        project=ProjectName.fake(),
        status=IssueStatusName.fake(),
        milestone=None,
        blocks=(),
        blocked_by=(),
    )


def test_a_created_issue_reads_back_as_it_was_given(
    tracker: TicketTracker,
    backlog: Backlog,
    creating: Creating,
) -> None:
    new = new_issue(IssueTitle("created: full")).model_copy(
        update={
            "description": IssueDescription.fake(),
            "labels": LabelNames((LabelName("backend"),)),
            "assignee": backlog.assignee,
            "status": IssueStatusName("in progress"),
            "milestone": Milestone.fake(),
        }
    )
    identifier = creating(new).unwrap().identifier
    assert tracker.read_issue_detail(identifier).unwrap() == IssueDetail(
        issue=Issue(
            identifier=identifier,
            status=IssueStatusName("In Progress"),
            project=ProjectName.fake(),
            labels=LabelNames((LabelName("Backend"),)),
            grouped=GroupedLabels(()),
            assigned=Assigned(True),
        ),
        title=IssueTitle("created: full"),
        description=IssueDescription.fake(),
        assignee=backlog.assignee,
        milestone=MilestoneName.fake(),
        blocks=frozenset(),
        blocked_by=frozenset(),
    )


def test_a_created_issue_links_to_itself(creating: Creating) -> None:
    created = creating(new_issue(IssueTitle("created: link"))).unwrap()
    assert created.identifier.root in created.url.root


def test_an_issue_created_in_a_named_team_needs_no_project(
    tracker: TicketTracker, backlog: Backlog, creating: Creating
) -> None:
    new = new_issue(IssueTitle("created: team")).model_copy(
        update={"team": backlog.team, "project": None}
    )
    assert tracker.read_issue(creating(new).unwrap().identifier).unwrap().project is None


def test_creating_an_issue_without_a_team_or_project_is_refused(
    creating: Creating,
) -> None:
    refused = creating(
        new_issue(IssueTitle("created: nowhere")).model_copy(update={"project": None})
    )
    assert isinstance(refused, Err)
    assert "team or a project" in str(refused.error)


def test_creating_an_issue_in_an_unknown_team_is_refused(
    creating: Creating,
) -> None:
    unknown = TeamKey("NOSUCHTEAM")
    new = new_issue(IssueTitle("created: unknown team")).model_copy(update={"team": unknown})
    refused = creating(new)
    assert isinstance(refused, Err)
    assert unknown.root in str(refused.error)


def test_creating_an_issue_in_an_unknown_project_is_refused(
    creating: Creating,
) -> None:
    unknown = ProjectName("No such project")
    new = new_issue(IssueTitle("created: unknown project")).model_copy(update={"project": unknown})
    refused = creating(new)
    assert isinstance(refused, Err)
    assert unknown.root in str(refused.error)


def test_creating_an_issue_with_an_unknown_status_is_refused(
    creating: Creating,
) -> None:
    unknown = IssueStatusName("No such status")
    new = new_issue(IssueTitle("created: unknown status")).model_copy(update={"status": unknown})
    refused = creating(new)
    assert isinstance(refused, Err)
    assert unknown.root in str(refused.error)


def test_a_created_issue_blocks_and_is_blocked_by_the_issues_it_names(
    tracker: TicketTracker, creating: Creating
) -> None:
    blocked = creating(new_issue(IssueTitle("created: blocked"))).unwrap().identifier
    blocker = creating(new_issue(IssueTitle("created: blocker"))).unwrap().identifier
    middle = (
        creating(
            new_issue(IssueTitle("created: middle")).model_copy(
                update={"blocks": (blocked,), "blocked_by": (blocker,)}
            )
        )
        .unwrap()
        .identifier
    )
    assert (tracker.blockers(middle).unwrap(), tracker.blockers(blocked).unwrap()) == (
        (blocker,),
        (middle,),
    )


def test_an_update_adds_the_issues_it_blocks_and_is_blocked_by(
    tracker: TicketTracker, creating: Creating
) -> None:
    blocked = creating(new_issue(IssueTitle("updated: blocked"))).unwrap().identifier
    blocker = creating(new_issue(IssueTitle("updated: blocker"))).unwrap().identifier
    middle = creating(new_issue(IssueTitle("updated: middle"))).unwrap().identifier
    tracker.update_issue(
        middle,
        IssueUpdate.nothing().model_copy(update={"blocks": (blocked,), "blocked_by": (blocker,)}),
    ).unwrap()
    assert (tracker.blockers(middle).unwrap(), tracker.blockers(blocked).unwrap()) == (
        (blocker,),
        (middle,),
    )


def rival_of(holder: ClaimHolder) -> ClaimHolder:
    return holder.model_copy(update={"host": HostName("bob-mbp.local")})


def holders(claims: Claims) -> tuple[ClaimHolder, ...]:
    return tuple(claim.holder for claim in claims.root)


def test_claims_read_back_earliest_first(claims: ClaimRegistry, backlog: Backlog) -> None:
    ticket = backlog.identifier(Seed.recent)
    _ = claims.post(ticket, ClaimHolder.fake())
    _ = claims.post(ticket, rival_of(ClaimHolder.fake()))
    assert holders(claims.claims(ticket).unwrap()) == (
        ClaimHolder.fake(),
        rival_of(ClaimHolder.fake()),
    )


def test_a_withdrawn_claim_is_gone(claims: ClaimRegistry, backlog: Backlog) -> None:
    ticket = backlog.identifier(Seed.recent)
    posted = claims.post(ticket, ClaimHolder.fake()).unwrap()
    kept = claims.post(ticket, rival_of(ClaimHolder.fake())).unwrap()
    claims.withdraw(ticket, posted).unwrap()
    assert claims.claims(ticket).unwrap().ids() == (kept,)


def test_an_unclaimed_ticket_has_no_claims(claims: ClaimRegistry, backlog: Backlog) -> None:
    assert claims.claims(backlog.identifier(Seed.recent)).unwrap() == Claims(())


# Both claimers must pass the check for a holder before either posts, or no race is run.
class RacedRegistry(ClaimRegistry):
    def __init__(self, inner: ClaimRegistry, rival: Callable[[], object]) -> None:
        self._inner = inner
        self._rival: Callable[[], object] | None = rival

    @override
    def claims(self, ticket: IssueIdentifier) -> Result[Claims, TicketTrackerError]:
        return self._inner.claims(ticket)

    @override
    def post(
        self, ticket: IssueIdentifier, holder: ClaimHolder
    ) -> Result[ClaimId, TicketTrackerError]:
        rival, self._rival = self._rival, None
        if rival is not None:
            _ = rival()
        return self._inner.post(ticket, holder)

    @override
    def withdraw(self, ticket: IssueIdentifier, claim: ClaimId) -> Result[None, TicketTrackerError]:
        return self._inner.withdraw(ticket, claim)


def test_of_two_racing_claimers_exactly_one_wins(
    tracker: TicketTracker, claims: ClaimRegistry, backlog: Backlog
) -> None:
    ticket = backlog.identifier(Seed.recent)
    first = ClaimRequest.fake().model_copy(
        update={"ticket": ticket, "status": tracker.read_issue(ticket).unwrap().status}
    )
    second = first.model_copy(update={"holder": rival_of(first.holder)})
    raced = RacedRegistry(claims, lambda: Claiming.claim_ticket(claims, second))
    lost = Claiming.claim_ticket(raced, first)
    assert isinstance(lost.error, ClaimLostError)
    assert re.search(re.escape(second.holder.host.root), str(lost.error))
    assert holders(claims.claims(ticket).unwrap()) == (second.holder,)


def test_a_claim_on_a_finished_ticket_reads_as_released(
    tracker: TicketTracker, claims: ClaimRegistry, backlog: Backlog
) -> None:
    ticket = backlog.identifier(Seed.recent)
    _ = claims.post(ticket, ClaimHolder.fake())
    tracker.update_issue(
        ticket, IssueUpdate.nothing().model_copy(update={"status": IssueStatusName("Canceled")})
    ).unwrap()
    assert (
        claims.claims(ticket).unwrap().holding(tracker.read_issue(ticket).unwrap().status) is None
    )
