from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from linear_python_client import (
    FindProjectRequest,
    IssueCreateRequest,
    IssueLabelsRequest,
    IssuesRequest,
    LinearClient,
)
from pydantic import AliasPath, Field

from mb_workflow.b_core.c_secondary_ports.issue_tracker import (
    FakeIssueTracker,
    IssueTrackerError,
    TrackedIssue,
)
from mb_workflow.b_core.d_domain_model.issue import (
    Assigned,
    Assignee,
    CreatedAfter,
    CreatedOn,
    Creator,
    Issue,
    IssueDescription,
    IssueDetail,
    IssueFilter,
    IssueIdentifier,
    IssueTitle,
    LabelName,
    LabelNames,
    ProjectName,
    StatusName,
)
from mb_workflow.c_infrastructure.credentials import CredentialsDirectory, RepositorySlug
from mb_workflow.c_infrastructure.linear import Linear
from mb_workflow.c_infrastructure.shell import ExistingDirectory, Shell
from mb_workflow.d_lib.models import Model, Payload, Value

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.issue_tracker import IssueTracker


class Seed(StrEnum):
    recent = "recent"
    old = "old"
    newest = "newest"
    done = "done"


class SeededIssue(Model):
    seed: Seed
    created_on: CreatedOn
    status: StatusName
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
            issue=self.issue(identifier), title=self.title(), description=self.description
        )


def workspace_labels() -> LabelNames:
    return LabelNames(tuple(LabelName(name) for name in ("Backend", "d-grill", "d-implement")))


def seeded(seed: Seed, created: CreatedOn) -> SeededIssue:
    return SeededIssue(
        seed=seed,
        created_on=created,
        status=StatusName.fake(),
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
            status=StatusName("Done"),
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

    def picked(self, wanted: IssueFilter, tracker: IssueTracker) -> tuple[Seed, ...]:
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


def ensure_project(client: LinearClient, team: TeamId, project: ProjectName) -> None:
    if client.find_project(FindProjectRequest(name=project.root)).project is not None:
        return
    _ = client.execute(
        "mutation($name: String!, $team: String!) {"
        " projectCreate(input: { name: $name, teamIds: [$team] }) { success } }",
        {"name": project.root, "team": team.root},
    )


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


# Seeded once per session; a test only ever changes labels and the assignee, which reset() restores.
@pytest.fixture(scope="session")
def linear_backlog(linear_client: LinearClient) -> Backlog:
    team = Workspace.of(linear_client).teams[0].id
    ensure_labels(linear_client, workspace_labels())
    ensure_project(linear_client, team, ProjectName.fake())
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
    for planted in seeds():
        identifier = backlog.identifier(planted.seed)
        tracker.set_labels(identifier, planted.labels)
        _ = client.execute(
            "mutation($id: String!, $description: String) {"
            " issueUpdate(id: $id, input: { assigneeId: null, description: $description })"
            " { success } }",
            {
                "id": identifier.root,
                "description": planted.description.root if planted.description else None,
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
def tracker(kind: TrackerKind, backlog: Backlog, request: pytest.FixtureRequest) -> IssueTracker:
    if kind == TrackerKind.linear:
        return Linear(request.getfixturevalue("linear_client"))
    return FakeIssueTracker(
        workspace_labels(),
        tuple(
            TrackedIssue(
                issue=planted.issue(backlog.identifier(planted.seed)),
                title=planted.title(),
                description=planted.description,
                creator=backlog.creator,
                created_on=planted.created_on,
            )
            for planted in seeds()
        ),
    )


def test_every_workspace_label_is_listed(tracker: IssueTracker) -> None:
    assert tracker.workspace_labels().unmatched(workspace_labels()) == LabelNames(())


def test_the_filter_picks_the_issues_one_creator_made_since_a_date(
    tracker: IssueTracker, backlog: Backlog
) -> None:
    since = IssueFilter(creator=backlog.creator, created_after=CreatedAfter(date(2026, 8, 9)))
    assert backlog.picked(since, tracker) == (Seed.recent, Seed.newest, Seed.done)


def test_the_filter_skips_issues_another_creator_made(
    tracker: IssueTracker, backlog: Backlog
) -> None:
    other = IssueFilter(
        creator=Creator("someone@flowbase.io"), created_after=CreatedAfter(date(2026, 8, 9))
    )
    assert backlog.picked(other, tracker) == ()


def test_the_filter_start_date_is_inclusive(tracker: IssueTracker, backlog: Backlog) -> None:
    after = IssueFilter(creator=backlog.creator, created_after=CreatedAfter(date(2026, 9, 2)))
    assert backlog.picked(after, tracker) == (Seed.newest,)


def test_reads_an_issue_back_as_it_was_given(tracker: IssueTracker, backlog: Backlog) -> None:
    assert tracker.read_issue(backlog.identifier(Seed.done)) == backlog.issue(Seed.done)


def test_an_issue_without_a_project_carries_none(tracker: IssueTracker, backlog: Backlog) -> None:
    assert tracker.read_issue(backlog.identifier(Seed.done)).project is None


def test_a_project_survives_the_round_trip(tracker: IssueTracker, backlog: Backlog) -> None:
    assert tracker.read_issue(backlog.identifier(Seed.recent)).project == ProjectName.fake()


def test_reading_an_unknown_issue_is_refused(tracker: IssueTracker) -> None:
    with pytest.raises(IssueTrackerError):
        _ = tracker.read_issue(IssueIdentifier("E-404"))


def test_viewing_an_issue_carries_its_title_and_description(
    tracker: IssueTracker, backlog: Backlog
) -> None:
    assert tracker.read_issue_detail(backlog.identifier(Seed.recent)) == backlog.detail(Seed.recent)


def test_an_issue_without_a_description_carries_none(
    tracker: IssueTracker, backlog: Backlog
) -> None:
    assert tracker.read_issue_detail(backlog.identifier(Seed.done)).description is None


def test_viewing_an_unknown_issue_is_refused(tracker: IssueTracker) -> None:
    with pytest.raises(IssueTrackerError):
        _ = tracker.read_issue_detail(IssueIdentifier("E-404"))


def test_an_added_label_joins_the_ones_already_there(
    tracker: IssueTracker, backlog: Backlog
) -> None:
    tracker.add_label(backlog.identifier(Seed.done), LabelName.fake())
    assert set(tracker.read_issue(backlog.identifier(Seed.done)).labels.root) == {
        LabelName("d-grill"),
        LabelName.fake(),
    }


def test_adding_a_label_twice_carries_it_once(tracker: IssueTracker, backlog: Backlog) -> None:
    tracker.add_label(backlog.identifier(Seed.recent), LabelName.fake())
    tracker.add_label(backlog.identifier(Seed.recent), LabelName.fake())
    assert tracker.read_issue(backlog.identifier(Seed.recent)).labels == LabelNames.fake()


def test_adding_an_unknown_label_is_refused(tracker: IssueTracker, backlog: Backlog) -> None:
    with pytest.raises(IssueTrackerError):
        tracker.add_label(backlog.identifier(Seed.recent), LabelName("Frontend"))


def test_setting_labels_replaces_the_ones_there(tracker: IssueTracker, backlog: Backlog) -> None:
    tracker.set_labels(backlog.identifier(Seed.done), LabelNames((LabelName("Backend"),)))
    assert tracker.read_issue(backlog.identifier(Seed.done)).labels == LabelNames(
        (LabelName("Backend"),)
    )


def test_setting_no_labels_clears_them(tracker: IssueTracker, backlog: Backlog) -> None:
    tracker.set_labels(backlog.identifier(Seed.done), LabelNames(()))
    assert tracker.read_issue(backlog.identifier(Seed.done)).labels == LabelNames(())


def test_setting_an_unknown_label_is_refused(tracker: IssueTracker, backlog: Backlog) -> None:
    with pytest.raises(IssueTrackerError):
        tracker.set_labels(backlog.identifier(Seed.done), LabelNames((LabelName("Frontend"),)))


def test_an_issue_starts_unassigned(tracker: IssueTracker, backlog: Backlog) -> None:
    assert tracker.read_issue(backlog.identifier(Seed.recent)).assigned == Assigned(False)


def test_assigning_an_issue_leaves_it_assigned(tracker: IssueTracker, backlog: Backlog) -> None:
    tracker.assign(backlog.identifier(Seed.recent), backlog.assignee)
    assert tracker.read_issue(backlog.identifier(Seed.recent)).assigned == Assigned(True)


def test_assigning_an_unknown_issue_is_refused(tracker: IssueTracker, backlog: Backlog) -> None:
    with pytest.raises(IssueTrackerError):
        tracker.assign(IssueIdentifier("E-404"), backlog.assignee)


def test_a_label_is_found_whatever_its_case(tracker: IssueTracker, backlog: Backlog) -> None:
    tracker.add_label(backlog.identifier(Seed.recent), LabelName("D-IMPLEMENT"))
    assert tracker.read_issue(backlog.identifier(Seed.recent)).labels == LabelNames.fake()


def test_setting_labels_takes_the_workspace_spelling(
    tracker: IssueTracker, backlog: Backlog
) -> None:
    tracker.set_labels(backlog.identifier(Seed.recent), LabelNames((LabelName("backend"),)))
    assert tracker.read_issue(backlog.identifier(Seed.recent)).labels == LabelNames(
        (LabelName("Backend"),)
    )


def test_adding_a_label_in_another_case_carries_it_once(
    tracker: IssueTracker, backlog: Backlog
) -> None:
    tracker.add_label(backlog.identifier(Seed.recent), LabelName.fake())
    tracker.add_label(backlog.identifier(Seed.recent), LabelName("D-Implement"))
    assert tracker.read_issue(backlog.identifier(Seed.recent)).labels == LabelNames.fake()
