from typing import TYPE_CHECKING, override

from safe_result import Err, Ok, Result

from mb_workflow.b_core.c_secondary_ports.claims import ClaimRegistry
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker, TicketTrackerError
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
    from mb_workflow.c_infrastructure.credentials import CredentialsError, RepositorySlugError
    from mb_workflow.c_infrastructure.linear import LinearApiKey

    type KeyRead = Callable[[], Result[LinearApiKey, CredentialsError | RepositorySlugError]]


class LinearKey:
    @staticmethod
    def read(key: KeyRead) -> Result[LinearApiKey, TicketTrackerError]:
        match key():
            case Ok(read):
                return Ok(read)
            case Err(error):
                return Err(TicketTrackerError(str(error)))


class LazyLinearClaims(ClaimRegistry):
    def __init__(self, key: KeyRead) -> None:
        self._key = key
        self._connected: LinearClaims | None = None

    @override
    def claims(self, ticket: IssueIdentifier) -> Result[Claims, TicketTrackerError]:
        match self._registry():
            case Ok(registry):
                return registry.claims(ticket)
            case Err() as failed:
                return failed

    @override
    def post(
        self, ticket: IssueIdentifier, holder: ClaimHolder
    ) -> Result[ClaimId, TicketTrackerError]:
        match self._registry():
            case Ok(registry):
                return registry.post(ticket, holder)
            case Err() as failed:
                return failed

    @override
    def withdraw(self, ticket: IssueIdentifier, claim: ClaimId) -> Result[None, TicketTrackerError]:
        match self._registry():
            case Ok(registry):
                return registry.withdraw(ticket, claim)
            case Err() as failed:
                return failed

    def _registry(self) -> Result[LinearClaims, TicketTrackerError]:
        if self._connected is None:
            match LinearKey.read(self._key):
                case Ok(key):
                    self._connected = LinearClaims.connected(key)
                case Err() as failed:
                    return failed
        return Ok(self._connected)


class LazyLinear(TicketTracker):
    def __init__(self, key: KeyRead) -> None:
        self._key = key
        self._connected: Linear | None = None

    @override
    def workspace_labels(self) -> Result[LabelNames, TicketTrackerError]:
        return self._called(lambda tracker: tracker.workspace_labels())

    @override
    def group_labels(
        self, group: LabelGroupName, team: TeamKey | None
    ) -> Result[ColoredLabels, TicketTrackerError]:
        return self._called(lambda tracker: tracker.group_labels(group, team))

    @override
    def label_group(self, label: LabelName) -> Result[LabelGroupName | None, TicketTrackerError]:
        return self._called(lambda tracker: tracker.label_group(label))

    @override
    def create_group_labels(
        self, group: LabelGroupName, labels: ColoredLabels, team: TeamKey | None
    ) -> Result[None, TicketTrackerError]:
        return self._called(lambda tracker: tracker.create_group_labels(group, labels, team))

    @override
    def recolor_group_labels(
        self, group: LabelGroupName, labels: ColoredLabels, team: TeamKey | None
    ) -> Result[None, TicketTrackerError]:
        return self._called(lambda tracker: tracker.recolor_group_labels(group, labels, team))

    @override
    def rename_group_label(
        self, group: LabelGroupName, label: LabelName, renamed: LabelName, team: TeamKey | None
    ) -> Result[None, TicketTrackerError]:
        return self._called(lambda tracker: tracker.rename_group_label(group, label, renamed, team))

    @override
    def delete_group_label(
        self, group: LabelGroupName, label: LabelName, team: TeamKey | None
    ) -> Result[None, TicketTrackerError]:
        return self._called(lambda tracker: tracker.delete_group_label(group, label, team))

    @override
    def labelled_ticket_count(
        self, group: LabelGroupName, label: LabelName, team: TeamKey | None
    ) -> Result[TicketCount, TicketTrackerError]:
        return self._called(lambda tracker: tracker.labelled_ticket_count(group, label, team))

    @override
    def team_named(self, name: TeamName) -> Result[TeamKey, TicketTrackerError]:
        return self._called(lambda tracker: tracker.team_named(name))

    @override
    def team_of(self, issue: IssueIdentifier) -> Result[TeamKey, TicketTrackerError]:
        return self._called(lambda tracker: tracker.team_of(issue))

    @override
    def list_issues(self, wanted: IssueFilter) -> Result[Issues, TicketTrackerError]:
        return self._called(lambda tracker: tracker.list_issues(wanted))

    @override
    def unblocked_view_tickets(self, view: ViewSlug) -> Result[PoolTickets, TicketTrackerError]:
        return self._called(lambda tracker: tracker.unblocked_view_tickets(view))

    @override
    def labelled_issues(
        self, label: LabelName, excluding: StatusTypes
    ) -> Result[Issues, TicketTrackerError]:
        return self._called(lambda tracker: tracker.labelled_issues(label, excluding))

    @override
    def read_issue(self, issue: IssueIdentifier) -> Result[Issue, TicketTrackerError]:
        return self._called(lambda tracker: tracker.read_issue(issue))

    @override
    def read_issue_detail(self, issue: IssueIdentifier) -> Result[IssueDetail, TicketTrackerError]:
        return self._called(lambda tracker: tracker.read_issue_detail(issue))

    @override
    def add_label(
        self, issue: IssueIdentifier, label: LabelName
    ) -> Result[None, TicketTrackerError]:
        return self._called(lambda tracker: tracker.add_label(issue, label))

    @override
    def remove_label(
        self, issue: IssueIdentifier, label: LabelName
    ) -> Result[None, TicketTrackerError]:
        return self._called(lambda tracker: tracker.remove_label(issue, label))

    @override
    def set_labels(
        self, issue: IssueIdentifier, labels: LabelNames
    ) -> Result[None, TicketTrackerError]:
        return self._called(lambda tracker: tracker.set_labels(issue, labels))

    @override
    def assign(
        self, issue: IssueIdentifier, assignee: Assignee
    ) -> Result[None, TicketTrackerError]:
        return self._called(lambda tracker: tracker.assign(issue, assignee))

    @override
    def update_issue(
        self, issue: IssueIdentifier, update: IssueUpdate
    ) -> Result[None, TicketTrackerError]:
        return self._called(lambda tracker: tracker.update_issue(issue, update))

    @override
    def create_issue(self, new: NewIssue) -> Result[CreatedIssue, TicketTrackerError]:
        return self._called(lambda tracker: tracker.create_issue(new))

    @override
    def blockers(
        self, issue: IssueIdentifier
    ) -> Result[tuple[IssueIdentifier, ...], TicketTrackerError]:
        return self._called(lambda tracker: tracker.blockers(issue))

    @override
    def viewer(self) -> Result[Assignee, TicketTrackerError]:
        return self._called(lambda tracker: tracker.viewer())

    def _called[T](
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
