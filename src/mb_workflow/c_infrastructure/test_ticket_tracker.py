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
    FakePause,
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
    CreatedOn,
    Creator,
    Issue,
    IssueDescription,
    IssueDetail,
    IssueFilter,
    IssueIdentifier,
    IssueStatusName,
    IssueTitle,
    IssueUpdate,
    LabelName,
    LabelNames,
    Milestone,
    MilestoneName,
    MilestoneNames,
    Project,
    ProjectName,
    Projects,
    StatusNames,
)
from mb_workflow.c_infrastructure.credentials import CredentialsDirectory, RepositorySlug
from mb_workflow.c_infrastructure.linear import (
    Linear,
    MilestonePayload,
    ProjectId,
)
from mb_workflow.c_infrastructure.linear_claims import LinearClaims
from mb_workflow.c_infrastructure.shell import ExistingDirectory, Shell
from mb_workflow.d_lib.models import Model, Payload, Value

if TYPE_CHECKING:
    from collections.abc import Callable

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

    def issue(self, identifier: IssueIdentifier) -> Issue:
        return Issue(
            identifier=identifier,
            status=self.status,
            project=self.project,
            labels=self.labels,
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


def seeded(seed: Seed, created: CreatedOn) -> SeededIssue:
    return SeededIssue(
        seed=seed,
        created_on=created,
        status=IssueStatusName.fake(),
        project=ProjectName.fake(),
        labels=LabelNames(()),
        description=IssueDescription.fake(),
    )


def seeds() -> tuple[SeededIssue, ...]:
    return (
        seeded(Seed.recent, CreatedOn(date(2026, 9, 1))),
        seeded(Seed.old, CreatedOn(date(2026, 8, 1))),
        seeded(Seed.newest, CreatedOn(date(2026, 9, 2))),
        SeededIssue(
            seed=Seed.done,
            created_on=CreatedOn.fake(),
            status=IssueStatusName("Done"),
            project=None,
            labels=LabelNames((LabelName("d-grill"),)),
            description=None,
        ),
    )


class Backlog(Model):
    identifiers: dict[Seed, IssueIdentifier]
    creator: Creator
    assignee: Assignee

    def identifier(self, seed: Seed) -> IssueIdentifier:
        return self.identifiers[seed]

    def issue(self, seed: Seed) -> Issue:
        return self.detail(seed).issue

    def detail(self, seed: Seed) -> IssueDetail:
        planted = next(planted for planted in seeds() if planted.seed == seed)
        return planted.detail(self.identifier(seed))

    def picked(self, wanted: IssueFilter, tracker: TicketTracker) -> tuple[Seed, ...]:
        swept = tracker.list_issues(wanted).identifiers()
        return tuple(seed for seed in Seed if self.identifier(seed) in swept)


class TeamId(Value[str]):
    @staticmethod
    def fake() -> TeamId:
        return TeamId("6f3c5a4e-1f0b-4b8e-9d7a-2c1e0f9b8a7d")


class WorkspaceKey(Value[str]):
    @staticmethod
    def fake() -> WorkspaceKey:
        return WorkspaceKey("mb-workflow-integration-test")


class Organization(Payload):
    url_key: WorkspaceKey

    @staticmethod
    def fake() -> Organization:
        return Organization(url_key=WorkspaceKey.fake())


class Team(Payload):
    id: TeamId

    @staticmethod
    def fake() -> Team:
        return Team(id=TeamId.fake())


class Workspace(Payload):
    organization: Organization
    teams: tuple[Team, ...] = Field(validation_alias=AliasPath("teams", "nodes"))

    @staticmethod
    def fake() -> Workspace:
        return Workspace(organization=Organization.fake(), teams=(Team.fake(),))

    @staticmethod
    def of(client: LinearClient) -> Workspace:
        return Workspace.model_validate(
            client.execute("{ organization { urlKey } teams { nodes { id } } }")
        )


class TrackerKind(StrEnum):
    fake = "fake"
    linear = "linear"


def fake_backlog() -> Backlog:
    return Backlog(
        identifiers={seed: IssueIdentifier(f"E-{n}") for n, seed in enumerate(Seed, start=1)},
        creator=Creator.fake(),
        assignee=Assignee.fake(),
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
            createdAt=f"{planted.created_on.root.isoformat()}T12:00:00Z",
        )
    ).issue
    if created is None or created.identifier is None:
        pytest.fail(f"Linear did not create {title}.")
    return IssueIdentifier(created.identifier)


# Seeded once per session; reset() restores whatever a test changes.
@pytest.fixture(scope="session")
def linear_backlog(linear_client: LinearClient) -> Backlog:
    team = Workspace.of(linear_client).teams[0].id
    ensure_labels(linear_client, workspace_labels())
    _ = ensure_project(linear_client, team, Project.fake())
    viewer = linear_client.viewer().viewer
    if viewer is None or viewer.email is None:
        pytest.fail("Linear did not say who the API key belongs to.")
    return Backlog(
        identifiers={
            planted.seed: ensure_issue(linear_client, team, planted) for planted in seeds()
        },
        creator=Creator(viewer.email),
        assignee=Assignee(viewer.email),
    )


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
            )
            for planted in seeds()
        ),
        Projects.fake(),
        StatusNames((*StatusNames.fake().root, *StatusNames.closed().root)),
        backlog.assignee,
    )


@pytest.fixture
def claims(kind: TrackerKind, request: pytest.FixtureRequest) -> ClaimRegistry:
    if kind == TrackerKind.linear:
        return LinearClaims(request.getfixturevalue("linear_client"))
    return FakeClaimRegistry()


def test_every_workspace_label_is_listed(tracker: TicketTracker) -> None:
    assert tracker.workspace_labels().unmatched(workspace_labels()) == LabelNames(())


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
    raced = RacedRegistry(claims, lambda: claim_ticket(claims, FakePause(), second))
    with pytest.raises(ClaimRefusedError, match="bob-mbp"):
        claim_ticket(raced, FakePause(), first)
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
