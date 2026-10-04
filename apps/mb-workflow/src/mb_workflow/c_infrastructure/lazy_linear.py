from typing import TYPE_CHECKING, override

from safe_result import Err, Ok, Result, safe_with

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
        TicketCount,
    )
    from mb_workflow.b_core.d_domain_model.pool import PoolTickets, ViewSlug
    from mb_workflow.c_infrastructure.linear import LinearApiKey


class LinearKey:
    @staticmethod
    def read(key: Callable[[], LinearApiKey]) -> Result[LinearApiKey, TicketTrackerError]:
        match safe_with(InvalidCredentialsError, MissingCredentialsError)(key)():
            case Ok(read):
                return Ok(read)
            case Err(error):
                return Err(TicketTrackerError(str(error)))


# Reads the key on first use, so a run that releases no claim needs no Linear credentials.
class LazyLinearClaims(ClaimRegistry):
    def __init__(self, key: Callable[[], LinearApiKey]) -> None:
        self._key = key
        self._connected: LinearClaims | None = None

    @override
    def claims(self, ticket: IssueIdentifier) -> Result[Claims, TicketTrackerError]:
        match self._registry():
            case Ok(registry):
                return registry.claims(ticket)
            case Err() as failed:
                return failed

    # Writes still raise; MB-130 returns their errors as values too.
    @override
    def post(self, ticket: IssueIdentifier, holder: ClaimHolder) -> ClaimId:
        return self._registry().unwrap().post(ticket, holder)

    @override
    def withdraw(self, ticket: IssueIdentifier, claim: ClaimId) -> None:
        self._registry().unwrap().withdraw(ticket, claim)

    def _registry(self) -> Result[LinearClaims, TicketTrackerError]:
        if self._connected is None:
            match LinearKey.read(self._key):
                case Ok(key):
                    self._connected = LinearClaims.connected(key)
                case Err() as failed:
                    return failed
        return Ok(self._connected)


# Reads the key on first use, so a run that releases no claim needs no Linear credentials.
class LazyLinear(TicketTracker):
    def __init__(self, key: Callable[[], LinearApiKey]) -> None:
        self._key = key
        self._connected: Linear | None = None

    @override
    def workspace_labels(self) -> Result[LabelNames, TicketTrackerError]:
        return self._looked_up(lambda tracker: tracker.workspace_labels())

    @override
    def group_labels(
        self, group: LabelGroupName, team: TeamKey | None
    ) -> Result[ColoredLabels, TicketTrackerError]:
        return self._looked_up(lambda tracker: tracker.group_labels(group, team))

    @override
    def label_group(self, label: LabelName) -> Result[LabelGroupName | None, TicketTrackerError]:
        return self._looked_up(lambda tracker: tracker.label_group(label))

    @override
    def create_group_labels(
        self, group: LabelGroupName, labels: ColoredLabels, team: TeamKey | None
    ) -> None:
        self._tracker().unwrap().create_group_labels(group, labels, team)

    @override
    def recolor_group_labels(
        self, group: LabelGroupName, labels: ColoredLabels, team: TeamKey | None
    ) -> None:
        self._tracker().unwrap().recolor_group_labels(group, labels, team)

    @override
    def rename_group_label(
        self, group: LabelGroupName, label: LabelName, renamed: LabelName, team: TeamKey | None
    ) -> Result[None, TicketTrackerError]:
        return self._looked_up(
            lambda tracker: tracker.rename_group_label(group, label, renamed, team)
        )

    @override
    def delete_group_label(
        self, group: LabelGroupName, label: LabelName, team: TeamKey | None
    ) -> Result[None, TicketTrackerError]:
        return self._looked_up(lambda tracker: tracker.delete_group_label(group, label, team))

    @override
    def labelled_ticket_count(
        self, group: LabelGroupName, label: LabelName, team: TeamKey | None
    ) -> Result[TicketCount, TicketTrackerError]:
        return self._looked_up(lambda tracker: tracker.labelled_ticket_count(group, label, team))

    @override
    def team_named(self, name: TeamName) -> Result[TeamKey, TicketTrackerError]:
        return self._looked_up(lambda tracker: tracker.team_named(name))

    @override
    def team_of(self, issue: IssueIdentifier) -> Result[TeamKey, TicketTrackerError]:
        return self._looked_up(lambda tracker: tracker.team_of(issue))

    @override
    def list_issues(self, wanted: IssueFilter) -> Result[Issues, TicketTrackerError]:
        return self._looked_up(lambda tracker: tracker.list_issues(wanted))

    @override
    def unblocked_view_tickets(self, view: ViewSlug) -> Result[PoolTickets, TicketTrackerError]:
        return self._looked_up(lambda tracker: tracker.unblocked_view_tickets(view))

    @override
    def labelled_issues(
        self, label: LabelName, excluding: StatusTypes
    ) -> Result[Issues, TicketTrackerError]:
        return self._looked_up(lambda tracker: tracker.labelled_issues(label, excluding))

    @override
    def read_issue(self, issue: IssueIdentifier) -> Result[Issue, TicketTrackerError]:
        return self._looked_up(lambda tracker: tracker.read_issue(issue))

    @override
    def read_issue_detail(self, issue: IssueIdentifier) -> Result[IssueDetail, TicketTrackerError]:
        return self._looked_up(lambda tracker: tracker.read_issue_detail(issue))

    # Writes still raise; MB-130 returns their errors as values too.
    @override
    def add_label(self, issue: IssueIdentifier, label: LabelName) -> None:
        self._tracker().unwrap().add_label(issue, label)

    @override
    def remove_label(self, issue: IssueIdentifier, label: LabelName) -> None:
        self._tracker().unwrap().remove_label(issue, label)

    @override
    def set_labels(self, issue: IssueIdentifier, labels: LabelNames) -> None:
        self._tracker().unwrap().set_labels(issue, labels)

    @override
    def assign(self, issue: IssueIdentifier, assignee: Assignee) -> None:
        self._tracker().unwrap().assign(issue, assignee)

    @override
    def update_issue(self, issue: IssueIdentifier, update: IssueUpdate) -> None:
        self._tracker().unwrap().update_issue(issue, update)

    @override
    def create_issue(self, new: NewIssue) -> CreatedIssue:
        return self._tracker().unwrap().create_issue(new)

    @override
    def blockers(
        self, issue: IssueIdentifier
    ) -> Result[tuple[IssueIdentifier, ...], TicketTrackerError]:
        return self._looked_up(lambda tracker: tracker.blockers(issue))

    @override
    def viewer(self) -> Result[Assignee, TicketTrackerError]:
        return self._looked_up(lambda tracker: tracker.viewer())

    def _looked_up[T](
        self, lookup: Callable[[Linear], Result[T, TicketTrackerError]]
    ) -> Result[T, TicketTrackerError]:
        match self._tracker():
            case Ok(tracker):
                return lookup(tracker)
            case Err() as failed:
                return failed

    def _tracker(self) -> Result[Linear, TicketTrackerError]:
        if self._connected is None:
            match LinearKey.read(self._key):
                case Ok(key):
                    self._connected = Linear.connected(key)
                case Err() as failed:
                    return failed
        return Ok(self._connected)
