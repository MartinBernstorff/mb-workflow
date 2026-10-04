import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from safe_result import Err, Ok, Result

from mb_workflow.b_core.b_domain_services.flow_label_check import FlowLabelCheck
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTrackerError
from mb_workflow.b_core.d_domain_model.flow import (
    Edges,
    EventName,
    FlowError,
    StateName,
    WorkflowChart,
    WorkspaceOpening,
)
from mb_workflow.b_core.d_domain_model.issue import IssueUpdate
from mb_workflow.d_lib.logging import Activity
from mb_workflow.d_lib.models import Value
from mb_workflow.d_lib.saga import SagaStep

if TYPE_CHECKING:
    from mb_workflow.b_core.b_domain_services.flow_label_check import MissingFlowLabelsError
    from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManagerError
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.issue import Issue, IssueIdentifier, IssueStatusName
    from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses
    from mb_workflow.b_core.d_domain_model.workspace import WorkspaceStatus

logger = logging.getLogger(__name__)


class Force(Value[bool]):
    @staticmethod
    def fake() -> Force:
        return Force(False)


class FlowTransition:
    @staticmethod
    def move_ticket(
        *,
        chart: type[WorkflowChart],
        store: WorkspaceStatusStore,
        tracker: TicketTracker,
        issue: IssueIdentifier,
        wanted: FlowLabels,
        statuses: TicketStatuses,
        event: EventName,
        force: Force,
    ) -> Result[
        StateName,
        FlowError | TicketTrackerError | MissingFlowLabelsError | WorkspaceManagerError,
    ]:
        edges = Edges.of_chart(chart)
        if force.root:
            target = edges.target_of(event)
        else:
            current = store.read()
            if isinstance(current, Err):
                return current
            target = edges.target_from(current.value, event)
        if isinstance(target, Err):
            return target
        put = FlowTransition.put_in_state(tracker, issue, wanted, statuses, target.value)
        if isinstance(put, Err):
            return put
        written = store.write(target.value)
        if isinstance(written, Err):
            return written
        return Ok(target.value)

    @staticmethod
    def put_in_state(
        tracker: TicketTracker,
        issue: IssueIdentifier,
        wanted: FlowLabels,
        statuses: TicketStatuses,
        state: StateName,
    ) -> Result[None, TicketTrackerError | MissingFlowLabelsError]:
        checked = FlowLabelCheck.require_for_issue(tracker, wanted, issue)
        if isinstance(checked, Err):
            return checked
        return FlowTransition.put_in_state_unchecked(tracker, issue, wanted, statuses, state)

    @staticmethod
    def put_in_state_unchecked(
        tracker: TicketTracker,
        issue: IssueIdentifier,
        wanted: FlowLabels,
        statuses: TicketStatuses,
        state: StateName,
    ) -> Result[None, TicketTrackerError]:
        held = tracker.read_issue(issue)
        if isinstance(held, Err):
            return held
        labels = wanted.relabelled(held.value.labels, state)
        return tracker.update_issue(
            issue,
            IssueUpdate.nothing().model_copy(
                update={"labels": labels, "status": statuses.of(state)}
            ),
        )


@dataclass(frozen=True)
class FlowStateStep(SagaStep[TicketTrackerError]):
    tracker: TicketTracker
    issue: IssueIdentifier
    wanted: FlowLabels
    statuses: TicketStatuses
    state: StateName
    previous_state: StateName | None
    previous_status: IssueStatusName

    @override
    def apply(self) -> Result[None, TicketTrackerError]:
        with Activity(f"Putting {self.issue.root} in {self.state.root}").logged(logger):
            return FlowTransition.put_in_state_unchecked(
                self.tracker, self.issue, self.wanted, self.statuses, self.state
            )

    @override
    def revert(self) -> Result[None, Exception]:
        held = self.tracker.read_issue(self.issue)
        if isinstance(held, Err):
            return held
        labels = (
            self.wanted.without_flow_labels(held.value.labels)
            if self.previous_state is None
            else self.wanted.relabelled(held.value.labels, self.previous_state)
        )
        with Activity(
            f"Moving {self.issue.root} back to"
            f" {'no flow state' if self.previous_state is None else self.previous_state.root}"
            f" and {self.previous_status.root}"
        ).logged(logger):
            return self.tracker.update_issue(
                self.issue,
                IssueUpdate.nothing().model_copy(
                    update={"labels": labels, "status": self.previous_status}
                ),
            )


# The state a ticket opens a workspace in, its status and board column there, and the steps
# that move it there; a ticket held elsewhere moves first, so its claim records the status it
# moves to.
@dataclass(frozen=True)
class OpeningEntry:
    state: StateName
    status: IssueStatusName
    column: WorkspaceStatus
    steps: tuple[SagaStep[TicketTrackerError], ...]

    @staticmethod
    def planned(
        *,
        tracker: TicketTracker,
        board: WorkspaceStatusStore,
        flow_labels: FlowLabels,
        statuses: TicketStatuses,
        issue: Issue,
        labelled_state: StateName | None,
        state: StateName,
    ) -> Result[OpeningEntry, TicketTrackerError | MissingFlowLabelsError | WorkspaceManagerError]:
        opened = WorkspaceOpening.state_opened_in(WorkflowChart, state)
        column = board.status_for(opened)
        if isinstance(column, Err):
            return column
        if labelled_state == opened:
            return Ok(
                OpeningEntry(state=opened, status=issue.status, column=column.value, steps=())
            )
        checked = FlowLabelCheck.require_for_issue(tracker, flow_labels, issue.identifier)
        if isinstance(checked, Err):
            return checked
        entering = FlowStateStep(
            tracker=tracker,
            issue=issue.identifier,
            wanted=flow_labels,
            statuses=statuses,
            state=opened,
            previous_state=labelled_state,
            previous_status=issue.status,
        )
        return Ok(
            OpeningEntry(
                state=opened, status=statuses.of(opened), column=column.value, steps=(entering,)
            )
        )
