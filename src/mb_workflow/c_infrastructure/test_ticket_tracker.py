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

from mb_workflow.b_core.c_secondary_ports.claims import (
    ClaimRefusedError,
    ClaimRegistry,
    ClaimRequest,
    FakeClaimRegistry,
    claim_ticket,
)
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
    FakeTicketTracker,
    TicketTrackerError,
    TrackedIssue,
)
from mb_workflow.b_core.d_domain_model.claim import ClaimHolder, ClaimId, Claims, HostName
from mb_workflow.b_core.d_domain_model.issue import (
    Assigned,
    Assignee,
    Cleared,
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
    LabelGroupName,
    LabelName,
    LabelNames,
    Milestone,
    MilestoneName,
    MilestoneNames,
    NewIssue,
    Project,
    ProjectName,
    Projects,
    StatusType,
    StatusTypes,
    Team,
    TeamKey,
)
from mb_workflow.b_core.d_domain_model.pool import PoolTicket, Priority, ViewSlug
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

    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker


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

    def detail(self, identifier: IssueIdentifier) -> IssueDetail:
        return IssueDetail(
            issue=self.issue(identifier),
            title=self.title(),
            description=self.description,
            assignee=None,
            milestone=None,
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

    def identifier(self, seed: Seed) -> IssueIdentifier:
        return self.identifiers[seed]

    def issue(self, seed: Seed) -> Issue:
        return self.detail(seed).issue

    def detail(self, seed: Seed) -> IssueDetail:
        planted = next(planted for planted in seeds() if planted.seed == seed)
        return planted.detail(self.identifier(seed))

    def ticket(self, seed: Seed) -> PoolTicket:
        planted = next(planted for planted in seeds() if planted.seed == seed)
        return PoolTicket(
            issue=self.issue(seed),
            priority=planted.priority,
        )

    def picked(self, wanted: IssueFilter, tracker: TicketTracker) -> tuple[Seed, ...]:
        swept = tracker.list_issues(wanted).identifiers()
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

    @staticmethod
    def fake() -> WorkspaceTeam:
        return WorkspaceTeam(id=TeamId.fake(), key=TeamKey.fake())


class Workspace(Payload):
    organization: Organization
    teams: tuple[WorkspaceTeam, ...] = Field(validation_alias=AliasPath("teams", "nodes"))

    @staticmethod
    def fake() -> Workspace:
        return Workspace(organization=Organization.fake(), teams=(WorkspaceTeam.fake(),))

    @staticmethod
    def of(client: LinearClient) -> Workspace:
        return Workspace.model_validate(
            client.execute("{ organization { urlKey } teams { nodes { id key } } }")
        )


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
    )


# A key for the production workspace would make this suite rewrite real issues.
@pytest.fixture(scope="session")
def linear_client() -> LinearClient:
    path = CredentialsDirectory.of_user().path_for(
        RepositorySlug.of_origin(Shell(ExistingDirectory(Path.cwd())))
    )
    key = path.credentials().linear.integration_test_api_key
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
    team = Workspace.of(linear_client).teams[0]
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
        for stale in claims.claims(identifier).root:
            claims.withdraw(identifier, stale.id)
        tracker.set_labels(identifier, planted.labels)
        tracker.update_issue(
            identifier, IssueUpdate.nothing().model_copy(update={"status": planted.status})
        )
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
        teams=(Team(key=backlog.team, projects=(ProjectName.fake(),)),),
    )


def drop_group(client: LinearClient, group: LabelGroupName) -> None:
    found = LabelGroupRead.model_validate(
        client.execute(
            "query($name: String!) { issueLabels(first: 1, filter:"
            " { name: { eqIgnoreCase: $name }, isGroup: { eq: true } })"
            " { nodes { id children(first: 250) { nodes { id name } } } } }",
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
    assert tracker.workspace_labels().unmatched(workspace_labels()) == LabelNames(())


GRILLING = LabelName("Grilling")
QA = LabelName("QA")


def test_a_created_group_lists_its_labels_back(groupless: TicketTracker) -> None:
    groupless.create_group_labels(LabelGroupName.fake(), LabelNames((GRILLING, QA)))
    assert set(groupless.group_labels(LabelGroupName.fake()).root) == set(
        LabelNames((GRILLING, QA)).root
    )


def test_labels_added_to_a_group_join_the_ones_there(groupless: TicketTracker) -> None:
    groupless.create_group_labels(LabelGroupName.fake(), LabelNames((GRILLING,)))
    groupless.create_group_labels(LabelGroupName.fake(), LabelNames((QA,)))
    assert set(groupless.group_labels(LabelGroupName.fake()).root) == set(
        LabelNames((GRILLING, QA)).root
    )


def test_a_group_that_does_not_exist_lists_no_labels(groupless: TicketTracker) -> None:
    assert groupless.group_labels(LabelGroupName.fake()) == LabelNames(())


def test_an_issue_carries_a_label_of_a_group(groupless: TicketTracker, backlog: Backlog) -> None:
    groupless.create_group_labels(LabelGroupName.fake(), LabelNames((GRILLING, QA)))
    groupless.set_labels(backlog.identifier(Seed.done), LabelNames((LabelName("d-grill"), QA)))
    assert set(groupless.read_issue(backlog.identifier(Seed.done)).labels.root) == set(
        LabelNames((LabelName("d-grill"), QA)).root
    )


def test_an_issue_reads_back_the_group_of_its_labels(
    groupless: TicketTracker, backlog: Backlog
) -> None:
    groupless.create_group_labels(LabelGroupName.fake(), LabelNames((GRILLING, QA)))
    groupless.set_labels(backlog.identifier(Seed.done), LabelNames((LabelName("d-grill"), QA)))
    assert groupless.read_issue(backlog.identifier(Seed.done)).grouped.in_group(
        LabelGroupName.fake()
    ) == LabelNames((QA,))


def test_an_issue_carrying_two_labels_of_one_group_is_refused(
    groupless: TicketTracker, backlog: Backlog
) -> None:
    groupless.create_group_labels(LabelGroupName.fake(), LabelNames((GRILLING, QA)))
    with pytest.raises(TicketTrackerError):
        groupless.set_labels(backlog.identifier(Seed.done), LabelNames((GRILLING, QA)))


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
    shown = tracker.unblocked_view_tickets(backlog.view).identifiers()
    return {seed for seed in Seed if backlog.identifier(seed) in shown}


def test_a_view_lists_its_unblocked_tickets_with_their_priority(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    assert set(tracker.unblocked_view_tickets(backlog.view).root) == {
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
    )
    assert Seed.recent in listed(tracker, backlog)


def test_reading_an_unknown_view_is_refused(tracker: TicketTracker) -> None:
    with pytest.raises(TicketTrackerError):
        _ = tracker.unblocked_view_tickets(ViewSlug("000000000000"))


def labelled_seeds(
    tracker: TicketTracker, backlog: Backlog, label: LabelName, excluding: StatusTypes
) -> set[Seed]:
    listed = tracker.labelled_issues(label, excluding).identifiers()
    return {seed for seed in Seed if backlog.identifier(seed) in listed}


def test_the_issues_carrying_a_label_are_listed(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.add_label(backlog.identifier(Seed.recent), LabelName("d-grill"))
    assert labelled_seeds(tracker, backlog, LabelName("d-grill"), StatusTypes(())) == {
        Seed.recent,
        Seed.done,
    }


def test_labelled_issues_of_an_excluded_status_type_are_left_out(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    for seed in (Seed.recent, Seed.old):
        tracker.add_label(backlog.identifier(seed), LabelName("d-grill"))
    tracker.update_issue(
        backlog.identifier(Seed.old),
        IssueUpdate.nothing().model_copy(update={"status": IssueStatusName("Canceled")}),
    )
    excluding = StatusTypes((StatusType.completed, StatusType.canceled))
    assert labelled_seeds(tracker, backlog, LabelName("d-grill"), excluding) == {Seed.recent}


def test_a_labelled_issue_is_found_whatever_the_label_case(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    assert labelled_seeds(tracker, backlog, LabelName("D-Grill"), StatusTypes(())) == {Seed.done}


def test_reads_an_issue_back_as_it_was_given(tracker: TicketTracker, backlog: Backlog) -> None:
    assert tracker.read_issue(backlog.identifier(Seed.done)) == backlog.issue(Seed.done)


def test_an_issue_without_a_project_carries_none(tracker: TicketTracker, backlog: Backlog) -> None:
    assert tracker.read_issue(backlog.identifier(Seed.done)).project is None


def test_a_project_survives_the_round_trip(tracker: TicketTracker, backlog: Backlog) -> None:
    assert tracker.read_issue(backlog.identifier(Seed.recent)).project == ProjectName.fake()


def test_reading_an_unknown_issue_is_refused(tracker: TicketTracker) -> None:
    with pytest.raises(TicketTrackerError):
        _ = tracker.read_issue(IssueIdentifier("E-404"))


def test_viewing_an_issue_carries_its_title_and_description(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    assert tracker.read_issue_detail(backlog.identifier(Seed.recent)) == backlog.detail(Seed.recent)


def test_an_issue_without_a_description_carries_none(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    assert tracker.read_issue_detail(backlog.identifier(Seed.done)).description is None


def test_viewing_an_unknown_issue_is_refused(tracker: TicketTracker) -> None:
    with pytest.raises(TicketTrackerError):
        _ = tracker.read_issue_detail(IssueIdentifier("E-404"))


def test_an_added_label_joins_the_ones_already_there(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    tracker.add_label(backlog.identifier(Seed.done), LabelName.fake())
    assert set(tracker.read_issue(backlog.identifier(Seed.done)).labels.root) == {
        LabelName("d-grill"),
        LabelName.fake(),
    }


def test_adding_a_label_twice_carries_it_once(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.add_label(backlog.identifier(Seed.recent), LabelName.fake())
    tracker.add_label(backlog.identifier(Seed.recent), LabelName.fake())
    assert tracker.read_issue(backlog.identifier(Seed.recent)).labels == LabelNames.fake()


def test_adding_an_unknown_label_is_refused(tracker: TicketTracker, backlog: Backlog) -> None:
    with pytest.raises(TicketTrackerError):
        tracker.add_label(backlog.identifier(Seed.recent), LabelName("Frontend"))


def test_a_removed_label_leaves_the_others(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.add_label(backlog.identifier(Seed.done), LabelName.fake())
    tracker.remove_label(backlog.identifier(Seed.done), LabelName("d-grill"))
    assert tracker.read_issue(backlog.identifier(Seed.done)).labels == LabelNames(
        (LabelName.fake(),)
    )


def test_removing_a_label_the_issue_lacks_leaves_it_unchanged(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    tracker.remove_label(backlog.identifier(Seed.done), LabelName.fake())
    assert tracker.read_issue(backlog.identifier(Seed.done)).labels == LabelNames(
        (LabelName("d-grill"),)
    )


def test_setting_labels_replaces_the_ones_there(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.set_labels(backlog.identifier(Seed.done), LabelNames((LabelName("Backend"),)))
    assert tracker.read_issue(backlog.identifier(Seed.done)).labels == LabelNames(
        (LabelName("Backend"),)
    )


def test_setting_no_labels_clears_them(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.set_labels(backlog.identifier(Seed.done), LabelNames(()))
    assert tracker.read_issue(backlog.identifier(Seed.done)).labels == LabelNames(())


def test_setting_an_unknown_label_is_refused(tracker: TicketTracker, backlog: Backlog) -> None:
    with pytest.raises(TicketTrackerError):
        tracker.set_labels(backlog.identifier(Seed.done), LabelNames((LabelName("Frontend"),)))


def test_an_issue_starts_unassigned(tracker: TicketTracker, backlog: Backlog) -> None:
    assert tracker.read_issue(backlog.identifier(Seed.recent)).assigned == Assigned(False)


def test_assigning_an_issue_leaves_it_assigned(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.assign(backlog.identifier(Seed.recent), backlog.assignee)
    assert tracker.read_issue(backlog.identifier(Seed.recent)).assigned == Assigned(True)


def test_assigning_an_unknown_issue_is_refused(tracker: TicketTracker, backlog: Backlog) -> None:
    with pytest.raises(TicketTrackerError):
        tracker.assign(IssueIdentifier("E-404"), backlog.assignee)


def test_a_label_is_found_whatever_its_case(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.add_label(backlog.identifier(Seed.recent), LabelName("D-IMPLEMENT"))
    assert tracker.read_issue(backlog.identifier(Seed.recent)).labels == LabelNames.fake()


def test_setting_labels_takes_the_workspace_spelling(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    tracker.set_labels(backlog.identifier(Seed.recent), LabelNames((LabelName("backend"),)))
    assert tracker.read_issue(backlog.identifier(Seed.recent)).labels == LabelNames(
        (LabelName("Backend"),)
    )


def test_adding_a_label_in_another_case_carries_it_once(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    tracker.add_label(backlog.identifier(Seed.recent), LabelName.fake())
    tracker.add_label(backlog.identifier(Seed.recent), LabelName("D-Implement"))
    assert tracker.read_issue(backlog.identifier(Seed.recent)).labels == LabelNames.fake()


def test_the_viewer_is_the_one_holding_the_key(tracker: TicketTracker, backlog: Backlog) -> None:
    assert tracker.viewer() == backlog.assignee


def test_an_update_sets_the_title_and_description(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.update_issue(
        backlog.identifier(Seed.done),
        IssueUpdate.nothing().model_copy(
            update={
                "title": IssueTitle("contract: renamed"),
                "description": IssueDescription("Rewritten."),
            }
        ),
    )
    detail = tracker.read_issue_detail(backlog.identifier(Seed.done))
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
    )
    assert tracker.read_issue(backlog.identifier(Seed.done)) == backlog.issue(Seed.done)


def test_an_update_replaces_the_labels(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.update_issue(
        backlog.identifier(Seed.done),
        IssueUpdate.nothing().model_copy(update={"labels": LabelNames((LabelName("backend"),))}),
    )
    assert tracker.read_issue(backlog.identifier(Seed.done)).labels == LabelNames(
        (LabelName("Backend"),)
    )


def test_an_update_with_an_unknown_label_is_refused(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    with pytest.raises(TicketTrackerError):
        tracker.update_issue(
            backlog.identifier(Seed.done),
            IssueUpdate.nothing().model_copy(
                update={"labels": LabelNames((LabelName("Frontend"),))}
            ),
        )


def test_an_update_names_the_assignee(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.update_issue(
        backlog.identifier(Seed.recent),
        IssueUpdate.nothing().model_copy(update={"assignee": backlog.assignee}),
    )
    detail = tracker.read_issue_detail(backlog.identifier(Seed.recent))
    assert (detail.assignee, detail.issue.assigned) == (backlog.assignee, Assigned(True))


def test_an_update_can_unassign(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.update_issue(
        backlog.identifier(Seed.recent),
        IssueUpdate.nothing().model_copy(update={"assignee": backlog.assignee}),
    )
    tracker.update_issue(
        backlog.identifier(Seed.recent),
        IssueUpdate.nothing().model_copy(update={"assignee": Cleared()}),
    )
    detail = tracker.read_issue_detail(backlog.identifier(Seed.recent))
    assert (detail.assignee, detail.issue.assigned) == (None, Assigned(False))


def test_an_update_moves_an_issue_into_a_project(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.update_issue(
        backlog.identifier(Seed.done),
        IssueUpdate.nothing().model_copy(update={"project": ProjectName.fake()}),
    )
    assert tracker.read_issue(backlog.identifier(Seed.done)).project == ProjectName.fake()


def test_an_update_can_take_an_issue_out_of_its_project(
    tracker: TicketTracker, backlog: Backlog
) -> None:
    tracker.update_issue(
        backlog.identifier(Seed.recent),
        IssueUpdate.nothing().model_copy(update={"project": Cleared()}),
    )
    assert tracker.read_issue(backlog.identifier(Seed.recent)).project is None


def test_moving_to_an_unknown_project_is_refused(tracker: TicketTracker, backlog: Backlog) -> None:
    with pytest.raises(TicketTrackerError):
        tracker.update_issue(
            backlog.identifier(Seed.recent),
            IssueUpdate.nothing().model_copy(update={"project": ProjectName("No such project")}),
        )


def test_an_update_sets_a_milestone(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.update_issue(
        backlog.identifier(Seed.recent),
        IssueUpdate.nothing().model_copy(update={"milestone": Milestone.fake()}),
    )
    assert tracker.read_issue_detail(backlog.identifier(Seed.recent)).milestone == (
        MilestoneName.fake()
    )


def test_an_update_can_clear_the_milestone(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.update_issue(
        backlog.identifier(Seed.recent),
        IssueUpdate.nothing().model_copy(update={"milestone": Milestone.fake()}),
    )
    tracker.update_issue(
        backlog.identifier(Seed.recent),
        IssueUpdate.nothing().model_copy(update={"milestone": Cleared()}),
    )
    assert tracker.read_issue_detail(backlog.identifier(Seed.recent)).milestone is None


def test_an_unknown_milestone_is_refused(tracker: TicketTracker, backlog: Backlog) -> None:
    unknown = Milestone(project=ProjectName.fake(), name=MilestoneName("No such milestone"))
    with pytest.raises(TicketTrackerError):
        tracker.update_issue(
            backlog.identifier(Seed.recent),
            IssueUpdate.nothing().model_copy(update={"milestone": unknown}),
        )


def test_an_update_moves_an_issue_to_a_status(tracker: TicketTracker, backlog: Backlog) -> None:
    tracker.update_issue(
        backlog.identifier(Seed.recent),
        IssueUpdate.nothing().model_copy(update={"status": IssueStatusName("in progress")}),
    )
    assert tracker.read_issue(backlog.identifier(Seed.recent)).status == IssueStatusName(
        "In Progress"
    )


def test_moving_to_an_unknown_status_is_refused(tracker: TicketTracker, backlog: Backlog) -> None:
    with pytest.raises(TicketTrackerError):
        tracker.update_issue(
            backlog.identifier(Seed.recent),
            IssueUpdate.nothing().model_copy(update={"status": IssueStatusName("No such status")}),
        )


# Created issues go to the trash afterwards, so they never join the seeds' labels or view.
@pytest.fixture
def creating(
    kind: TrackerKind, tracker: TicketTracker, request: pytest.FixtureRequest
) -> Generator[Callable[[NewIssue], CreatedIssue]]:
    made: list[IssueIdentifier] = []

    def create(new: NewIssue) -> CreatedIssue:
        created = tracker.create_issue(new)
        made.append(created.identifier)
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
    creating: Callable[[NewIssue], CreatedIssue],
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
    identifier = creating(new).identifier
    assert tracker.read_issue_detail(identifier) == IssueDetail(
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
    )


def test_a_created_issue_links_to_itself(creating: Callable[[NewIssue], CreatedIssue]) -> None:
    created = creating(new_issue(IssueTitle("created: link")))
    assert created.identifier.root in created.url.root


def test_an_issue_created_in_a_named_team_needs_no_project(
    tracker: TicketTracker, backlog: Backlog, creating: Callable[[NewIssue], CreatedIssue]
) -> None:
    new = new_issue(IssueTitle("created: team")).model_copy(
        update={"team": backlog.team, "project": None}
    )
    assert tracker.read_issue(creating(new).identifier).project is None


def test_creating_an_issue_without_a_team_or_project_is_refused(
    creating: Callable[[NewIssue], CreatedIssue],
) -> None:
    with pytest.raises(TicketTrackerError, match="team or a project"):
        _ = creating(new_issue(IssueTitle("created: nowhere")).model_copy(update={"project": None}))


def test_creating_an_issue_in_an_unknown_team_is_refused(
    creating: Callable[[NewIssue], CreatedIssue],
) -> None:
    new = new_issue(IssueTitle("created: unknown team")).model_copy(
        update={"team": TeamKey("NOSUCHTEAM")}
    )
    with pytest.raises(TicketTrackerError, match="NOSUCHTEAM"):
        _ = creating(new)


def test_creating_an_issue_in_an_unknown_project_is_refused(
    creating: Callable[[NewIssue], CreatedIssue],
) -> None:
    new = new_issue(IssueTitle("created: unknown project")).model_copy(
        update={"project": ProjectName("No such project")}
    )
    with pytest.raises(TicketTrackerError, match="No such project"):
        _ = creating(new)


def test_creating_an_issue_with_an_unknown_status_is_refused(
    creating: Callable[[NewIssue], CreatedIssue],
) -> None:
    new = new_issue(IssueTitle("created: unknown status")).model_copy(
        update={"status": IssueStatusName("No such status")}
    )
    with pytest.raises(TicketTrackerError, match="No such status"):
        _ = creating(new)


def test_a_created_issue_blocks_and_is_blocked_by_the_issues_it_names(
    tracker: TicketTracker, creating: Callable[[NewIssue], CreatedIssue]
) -> None:
    blocked = creating(new_issue(IssueTitle("created: blocked"))).identifier
    blocker = creating(new_issue(IssueTitle("created: blocker"))).identifier
    middle = creating(
        new_issue(IssueTitle("created: middle")).model_copy(
            update={"blocks": (blocked,), "blocked_by": (blocker,)}
        )
    ).identifier
    assert (tracker.blockers(middle), tracker.blockers(blocked)) == ((blocker,), (middle,))


def rival_of(holder: ClaimHolder) -> ClaimHolder:
    return holder.model_copy(update={"host": HostName("bob-mbp.local")})


def holders(claims: Claims) -> tuple[ClaimHolder, ...]:
    return tuple(claim.holder for claim in claims.root)


def test_claims_read_back_earliest_first(claims: ClaimRegistry, backlog: Backlog) -> None:
    ticket = backlog.identifier(Seed.recent)
    _ = claims.post(ticket, ClaimHolder.fake())
    _ = claims.post(ticket, rival_of(ClaimHolder.fake()))
    assert holders(claims.claims(ticket)) == (ClaimHolder.fake(), rival_of(ClaimHolder.fake()))


def test_a_withdrawn_claim_is_gone(claims: ClaimRegistry, backlog: Backlog) -> None:
    ticket = backlog.identifier(Seed.recent)
    posted = claims.post(ticket, ClaimHolder.fake())
    kept = claims.post(ticket, rival_of(ClaimHolder.fake()))
    claims.withdraw(ticket, posted)
    assert claims.claims(ticket).ids() == (kept,)


def test_an_unclaimed_ticket_has_no_claims(claims: ClaimRegistry, backlog: Backlog) -> None:
    assert claims.claims(backlog.identifier(Seed.recent)) == Claims(())


# Both claimers must pass the check for a holder before either posts, or no race is run.
class RacedRegistry(ClaimRegistry):
    def __init__(self, inner: ClaimRegistry, rival: Callable[[], None]) -> None:
        self._inner = inner
        self._rival: Callable[[], None] | None = rival

    @override
    def claims(self, ticket: IssueIdentifier) -> Claims:
        return self._inner.claims(ticket)

    @override
    def post(self, ticket: IssueIdentifier, holder: ClaimHolder) -> ClaimId:
        rival, self._rival = self._rival, None
        if rival is not None:
            rival()
        return self._inner.post(ticket, holder)

    @override
    def withdraw(self, ticket: IssueIdentifier, claim: ClaimId) -> None:
        self._inner.withdraw(ticket, claim)


def test_of_two_racing_claimers_exactly_one_wins(
    tracker: TicketTracker, claims: ClaimRegistry, backlog: Backlog
) -> None:
    ticket = backlog.identifier(Seed.recent)
    first = ClaimRequest.fake().model_copy(
        update={"ticket": ticket, "status": tracker.read_issue(ticket).status}
    )
    second = first.model_copy(update={"holder": rival_of(first.holder)})
    raced = RacedRegistry(claims, lambda: claim_ticket(claims, second))
    with pytest.raises(ClaimRefusedError, match="bob-mbp"):
        claim_ticket(raced, first)
    assert holders(claims.claims(ticket)) == (second.holder,)


def test_a_claim_on_a_finished_ticket_reads_as_released(
    tracker: TicketTracker, claims: ClaimRegistry, backlog: Backlog
) -> None:
    ticket = backlog.identifier(Seed.recent)
    _ = claims.post(ticket, ClaimHolder.fake())
    tracker.update_issue(
        ticket, IssueUpdate.nothing().model_copy(update={"status": IssueStatusName("Canceled")})
    )
    assert claims.claims(ticket).holding(tracker.read_issue(ticket).status) is None
