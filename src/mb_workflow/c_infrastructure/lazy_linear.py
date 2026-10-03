from typing import TYPE_CHECKING, override

from mb_workflow.b_core.c_secondary_ports.claims import ClaimRegistry
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker, TicketTrackerError
from mb_workflow.c_infrastructure.credentials import (
    InvalidCredentialsError,
    MissingCredentialsError,
)
from mb_workflow.c_infrastructure.linear import Linear
from mb_workflow.c_infrastructure.linear_claims import LinearClaims

if TYPE_CHECKING:
    from collections.abc import Callable

    from mb_workflow.b_core.d_domain_model.claim import ClaimHolder, ClaimId, Claims
    from mb_workflow.b_core.d_domain_model.issue import (
        Assignee,
        ColoredLabels,
        CreatedIssue,
        Issue,
        IssueDetail,
        IssueFilter,
        IssueIdentifier,
        Issues,
        IssueUpdate,
        LabelGroupName,
        LabelName,
        LabelNames,
        NewIssue,
        StatusTypes,
        TeamKey,
        TeamName,
    )
    from mb_workflow.b_core.d_domain_model.pool import PoolTickets, ViewSlug
    from mb_workflow.c_infrastructure.linear import LinearApiKey


def read_key(key: Callable[[], LinearApiKey]) -> LinearApiKey:
    try:
        return key()
    except (InvalidCredentialsError, MissingCredentialsError) as error:
        raise TicketTrackerError(str(error)) from error


# Reads the key on first use, so a run that releases no claim needs no Linear credentials.
class LazyLinearClaims(ClaimRegistry):
    def __init__(self, key: Callable[[], LinearApiKey]) -> None:
        self._key = key
        self._connected: LinearClaims | None = None

    @override
    def claims(self, ticket: IssueIdentifier) -> Claims:
        return self._registry().claims(ticket)

    @override
    def post(self, ticket: IssueIdentifier, holder: ClaimHolder) -> ClaimId:
        return self._registry().post(ticket, holder)

    @override
    def withdraw(self, ticket: IssueIdentifier, claim: ClaimId) -> None:
        self._registry().withdraw(ticket, claim)

    def _registry(self) -> LinearClaims:
        if self._connected is None:
            self._connected = LinearClaims.connected(read_key(self._key))
        return self._connected


# Reads the key on first use, so a run that releases no claim needs no Linear credentials.
class LazyLinear(TicketTracker):
    def __init__(self, key: Callable[[], LinearApiKey]) -> None:
        self._key = key
        self._connected: Linear | None = None

    @override
    def workspace_labels(self) -> LabelNames:
        return self._tracker().workspace_labels()

    @override
    def group_labels(self, group: LabelGroupName, team: TeamKey | None) -> ColoredLabels:
        return self._tracker().group_labels(group, team)

    @override
    def label_group(self, label: LabelName) -> LabelGroupName | None:
        return self._tracker().label_group(label)

    @override
    def create_group_labels(
        self, group: LabelGroupName, labels: ColoredLabels, team: TeamKey | None
    ) -> None:
        self._tracker().create_group_labels(group, labels, team)

    @override
    def team_named(self, name: TeamName) -> TeamKey:
        return self._tracker().team_named(name)

    @override
    def team_of(self, issue: IssueIdentifier) -> TeamKey:
        return self._tracker().team_of(issue)

    @override
    def list_issues(self, wanted: IssueFilter) -> Issues:
        return self._tracker().list_issues(wanted)

    @override
    def unblocked_view_tickets(self, view: ViewSlug) -> PoolTickets:
        return self._tracker().unblocked_view_tickets(view)

    @override
    def labelled_issues(self, label: LabelName, excluding: StatusTypes) -> Issues:
        return self._tracker().labelled_issues(label, excluding)

    @override
    def read_issue(self, issue: IssueIdentifier) -> Issue:
        return self._tracker().read_issue(issue)

    @override
    def read_issue_detail(self, issue: IssueIdentifier) -> IssueDetail:
        return self._tracker().read_issue_detail(issue)

    @override
    def add_label(self, issue: IssueIdentifier, label: LabelName) -> None:
        self._tracker().add_label(issue, label)

    @override
    def remove_label(self, issue: IssueIdentifier, label: LabelName) -> None:
        self._tracker().remove_label(issue, label)

    @override
    def set_labels(self, issue: IssueIdentifier, labels: LabelNames) -> None:
        self._tracker().set_labels(issue, labels)

    @override
    def assign(self, issue: IssueIdentifier, assignee: Assignee) -> None:
        self._tracker().assign(issue, assignee)

    @override
    def update_issue(self, issue: IssueIdentifier, update: IssueUpdate) -> None:
        self._tracker().update_issue(issue, update)

    @override
    def create_issue(self, new: NewIssue) -> CreatedIssue:
        return self._tracker().create_issue(new)

    @override
    def blockers(self, issue: IssueIdentifier) -> tuple[IssueIdentifier, ...]:
        return self._tracker().blockers(issue)

    @override
    def viewer(self) -> Assignee:
        return self._tracker().viewer()

    def _tracker(self) -> Linear:
        if self._connected is None:
            self._connected = Linear.connected(read_key(self._key))
        return self._connected
