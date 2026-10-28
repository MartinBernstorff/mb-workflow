import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, override

from safe_result import Err, Ok, Result

from mb_workflow.b_core.b_domain_services.flow_transition import OpeningEntry
from mb_workflow.b_core.b_domain_services.next_action import TicketState
from mb_workflow.b_core.b_domain_services.take_ticket import TicketTaking
from mb_workflow.b_core.c_secondary_ports.claims import ClaimRequest
from mb_workflow.b_core.c_secondary_ports.workspace_manager import (
    WorkspaceManagerError,
    WorkspaceNaming,
)
from mb_workflow.b_core.d_domain_model.claim import ClaimHolder, HostName, TakeOver
from mb_workflow.b_core.d_domain_model.flow import (
    AcceptedStates,
    AgentWork,
    AwaitingHuman,
    Finished,
    FlowError,
    StateName,
    WorkflowChart,
    WorkState,
)
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
from mb_workflow.b_core.d_domain_model.workspace import (
    Activate,
    AgentName,
    DisplayName,
    ProjectSelector,
    Submit,
    TerminalText,
    TimeoutMs,
    WorkspacePriority,
    WorkspaceStatus,
    WorktreeName,
)
from mb_workflow.d_lib.logging import Activity
from mb_workflow.d_lib.models import Model
from mb_workflow.d_lib.saga import Saga, SagaStep

if TYPE_CHECKING:
    from mb_workflow.b_core.b_domain_services.flow_label_check import MissingFlowLabelsError
    from mb_workflow.b_core.c_secondary_ports.claims import ClaimRefusedError, ClaimRegistry
    from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
        TicketTracker,
        TicketTrackerError,
    )
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManager
    from mb_workflow.b_core.d_domain_model.config import FlowSettings, WorkspaceSettings
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.issue import Issue
    from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses
    from mb_workflow.b_core.d_domain_model.workspace import OpenedWorktree

logger = logging.getLogger(__name__)


class PromptUndeliveredError(Exception):
    pass


# Split out so a drain can move on when a ticket got a worktree after it was listed.
class WorktreeExistsError(WorkspaceManagerError):
    pass


class WorktreeCreation(Model):
    project: ProjectSelector
    name: WorktreeName
    ticket: IssueIdentifier
    agent: AgentName | None
    status: WorkspaceStatus
    activate: Activate

    @staticmethod
    def fake() -> WorktreeCreation:
        return WorktreeCreation(
            project=ProjectSelector.fake(),
            name=WorktreeName.of_issue(IssueIdentifier.fake()),
            ticket=IssueIdentifier.fake(),
            agent=AgentName.claude(),
            status=WorkspaceStatus.fake(),
            activate=Activate.fake(),
        )


# Mutable, as it holds the opened worktree for start to read once the saga succeeds.
@dataclass
class WorktreeStep(SagaStep[WorkspaceManagerError]):
    manager: WorkspaceManager
    creation: WorktreeCreation
    _opened: OpenedWorktree | None = field(default=None, init=False)

    @override
    def apply(self) -> Result[None, WorkspaceManagerError]:
        with Activity(f"Creating worktree {self.creation.name.root}").logged(logger):
            created = self.manager.create_for_issue(
                self.creation.project,
                self.creation.name,
                self.creation.ticket,
                self.creation.agent,
                self.creation.status,
                activate=self.creation.activate,
            )
        if isinstance(created, Err):
            return created
        self._opened = created.value
        return Ok(None)

    # The last step of start, so no later failure ever reverts it.
    @override
    def revert(self) -> Result[None, Exception]:
        return Ok(None)

    def opened(self) -> Result[OpenedWorktree, WorkspaceManagerError]:
        if self._opened is None:
            return Err(
                WorkspaceManagerError(f"Worktree {self.creation.name.root} was not created.")
            )
        return Ok(self._opened)


class StartRequest(Model):
    ticket: IssueIdentifier
    # Typed with the ticket after it; the agent reads the flow's state descriptions to pick its work.
    prompt: TerminalText
    submit: Submit
    idle_timeout: TimeoutMs
    host: HostName
    take_over: TakeOver
    activate: Activate
    # The state to put a ticket without a flow label in; None leaves it to the flow label, or to the
    # unlabelled state when the ticket has none.
    state: StateName | None

    @staticmethod
    def fake() -> StartRequest:
        return StartRequest(
            ticket=IssueIdentifier.fake(),
            prompt=TerminalText("/work"),
            submit=Submit.fake(),
            idle_timeout=TimeoutMs.fake(),
            host=HostName.fake(),
            take_over=TakeOver.fake(),
            activate=Activate.fake(),
            state=None,
        )

    def prompt_for(self, action: AgentWork | AwaitingHuman) -> TerminalText | None:
        if isinstance(action, AwaitingHuman):
            return None
        return TerminalText(f"{self.prompt.root} {self.ticket.root}")

    def state_given(
        self, labelled_state: StateName | None, unlabelled: StateName
    ) -> Result[StateName, FlowError]:
        if labelled_state is not None:
            if self.state is not None:
                return Err(
                    FlowError(
                        f"{self.ticket.root} is already in {labelled_state.root};"
                        " move it with `mw flow` instead of --state."
                    )
                )
            return Ok(labelled_state)
        if self.state is None:
            return Ok(unlabelled)
        return TicketStart.startable_states().named_ignoring_case(self.state)


class TicketStart:
    @staticmethod
    def start_ticket(
        *,
        manager: WorkspaceManager,
        tracker: TicketTracker,
        claims: ClaimRegistry,
        board: WorkspaceStatusStore,
        workspace: WorkspaceSettings,
        flow_labels: FlowLabels,
        statuses: TicketStatuses,
        flow: FlowSettings,
        request: StartRequest,
    ) -> Result[
        None,
        FlowError
        | TicketTrackerError
        | ClaimRefusedError
        | MissingFlowLabelsError
        | WorkspaceManagerError,
    ]:
        # Checked before touching anything, so a ticket never gets a second worktree.
        unopened = TicketStart.require_no_worktree(manager, request.ticket)
        if isinstance(unopened, Err):
            return unopened
        with Activity(f"Reading {request.ticket.root}").logged(logger):
            read = tracker.read_issue_detail(request.ticket)
        if isinstance(read, Err):
            return read
        detail = read.value
        planned = TicketStart.planned_start(request, flow_labels, flow, detail.issue)
        if isinstance(planned, Err):
            return planned
        labelled_state, state, prompt = planned.value
        entering = OpeningEntry.planned(
            tracker=tracker,
            board=board,
            flow_labels=flow_labels,
            statuses=statuses,
            issue=detail.issue,
            labelled_state=labelled_state,
            state=state,
        )
        if isinstance(entering, Err):
            return entering
        entry = entering.value
        name = WorktreeName.of_issue(request.ticket)
        worktree_step = WorktreeStep(
            manager,
            WorktreeCreation(
                project=workspace.orca_project,
                name=name,
                ticket=request.ticket,
                agent=None if prompt is None else AgentName.claude(),
                status=entry.column,
                activate=request.activate,
            ),
        )
        taking_steps = TicketTaking.saga_steps(
            claims=claims,
            tracker=tracker,
            workspace=workspace,
            request=ClaimRequest(
                ticket=request.ticket,
                status=entry.status,
                holder=ClaimHolder(host=request.host, worktree=name),
                take_over=request.take_over,
            ),
            previous=detail.assignee,
        )
        return TicketStart.take_into_worktree(
            manager=manager,
            taking_steps=(*entry.steps, *taking_steps),
            worktree_step=worktree_step,
            display_name=DisplayName.of_issue(detail.title),
            priority=WorkspacePriority.of_ticket(detail.priority),
            prompt=prompt,
            request=request,
        )

    @staticmethod
    def require_no_worktree(
        manager: WorkspaceManager, ticket: IssueIdentifier
    ) -> Result[None, WorkspaceManagerError]:
        with Activity(f"Checking that no worktree is linked to {ticket.root}").logged(logger):
            listed = manager.worktrees()
        if isinstance(listed, Err):
            return listed
        linked = listed.value.linked_to(ticket)
        if linked is not None:
            return Err(
                WorktreeExistsError(
                    f"{ticket.root} already has worktree {linked.path.root}. Work it there, or"
                    " remove it with `mw workspace teardown` before starting the ticket again."
                )
            )
        return Ok(None)

    # Takes the ticket, opens its worktree, and types the prompt, if any, into it.
    @staticmethod
    def take_into_worktree(
        *,
        manager: WorkspaceManager,
        taking_steps: tuple[SagaStep[TicketTrackerError | ClaimRefusedError], ...],
        worktree_step: WorktreeStep,
        display_name: DisplayName,
        priority: WorkspacePriority,
        prompt: TerminalText | None,
        request: StartRequest,
    ) -> Result[None, TicketTrackerError | ClaimRefusedError | WorkspaceManagerError]:
        ran = Saga.run((*taking_steps, worktree_step))
        if isinstance(ran, Err):
            return ran
        opened = worktree_step.opened().unwrap()

        logger.info("Created worktree %s.", opened.worktree.path.root)
        with Activity(f"Naming worktree {worktree_step.creation.name.root}").logged(logger):
            WorkspaceNaming.set_display_name_or_warn(manager, opened.worktree.path, display_name)
        with Activity(f"Prioritising worktree {worktree_step.creation.name.root}").logged(logger):
            WorkspaceNaming.set_priority_or_warn(manager, opened.worktree.path, priority)
        return TicketStart.prompt_if_any(manager, opened, prompt, request)

    @staticmethod
    def prompt_if_any(
        manager: WorkspaceManager,
        opened: OpenedWorktree,
        prompt: TerminalText | None,
        request: StartRequest,
    ) -> Result[None, WorkspaceManagerError]:
        if prompt is None:
            return Ok(None)
        return TicketStart.send_prompt(
            manager, opened, prompt, request.idle_timeout, request.submit
        )

    # The flow state the ticket carries, the state it starts in, and the prompt that starts its
    # work.
    @staticmethod
    def planned_start(
        request: StartRequest, flow_labels: FlowLabels, flow: FlowSettings, issue: Issue
    ) -> Result[tuple[StateName | None, StateName, TerminalText | None], FlowError]:
        labelled = flow_labels.state_of(WorkflowChart, issue.grouped)
        if isinstance(labelled, Err):
            return labelled
        given = request.state_given(labelled.value, flow.unlabelled_state)
        if isinstance(given, Err):
            return given
        action = TicketStart.action_in(request.ticket, given.value)
        if isinstance(action, Err):
            return action
        return Ok((labelled.value, given.value, request.prompt_for(action.value)))

    @staticmethod
    def startable_states() -> AcceptedStates:
        return AcceptedStates(
            tuple(
                StateName(state.name)
                for state in WorkflowChart.states
                if isinstance(state, WorkState) and not isinstance(state.action, Finished)
            )
        )

    @staticmethod
    def action_in(
        ticket: IssueIdentifier, state: StateName
    ) -> Result[AgentWork | AwaitingHuman, FlowError]:
        found = TicketState.next_action(WorkflowChart, state)
        if isinstance(found, Err):
            return found
        action = found.value
        if isinstance(action, Finished):
            return Err(FlowError(f"The ticket is {state.root}, so there is no work left in it."))
        if isinstance(action, AwaitingHuman):
            logger.warning(
                "%s is in %s, which waits for a human, so no prompt is typed.",
                ticket.root,
                state.root,
            )
        else:
            logger.info("%s is in %s, which an agent works.", ticket.root, state.root)
        return Ok(action)

    @staticmethod
    def send_prompt(
        manager: WorkspaceManager,
        opened: OpenedWorktree,
        prompt: TerminalText,
        idle_timeout: TimeoutMs,
        submit: Submit,
    ) -> Result[None, WorkspaceManagerError]:
        if opened.terminal is None:
            raise PromptUndeliveredError("No agent terminal handle returned; prompt not typed.")

        with Activity("Waiting for the agent terminal to go idle").logged(logger):
            idle = manager.wait_for_idle(opened.terminal, idle_timeout)
        if isinstance(idle, Err):
            logger.warning("Agent terminal never went idle; typing the prompt anyway.")

        with Activity(f"{'Submitting' if submit.root else 'Typing'} {prompt.root}").logged(logger):
            return manager.send_text(opened.terminal, prompt, submit)
