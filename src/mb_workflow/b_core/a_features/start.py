import logging
from typing import TYPE_CHECKING, override

from safe_result import Err, Ok, Result

from mb_workflow.b_core.b_domain_services.flow_transition import put_in_state
from mb_workflow.b_core.b_domain_services.next_action import next_action
from mb_workflow.b_core.b_domain_services.take_ticket import TicketTaking
from mb_workflow.b_core.c_secondary_ports.claims import Claiming, ClaimRequest
from mb_workflow.b_core.c_secondary_ports.workspace_manager import (
    WorkspaceManagerError,
    set_display_name_or_warn,
)
from mb_workflow.b_core.d_domain_model.claim import ClaimHolder, HostName, TakeOver
from mb_workflow.b_core.d_domain_model.flow import (
    AcceptedStates,
    AwaitingHuman,
    Finished,
    FlowError,
    Skill,
    StateName,
    WorkflowChart,
)
from mb_workflow.b_core.d_domain_model.flow_labels import state_of
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
from mb_workflow.b_core.d_domain_model.workspace import (
    Activate,
    AgentName,
    DisplayName,
    ProjectSelector,
    Submit,
    TerminalText,
    TimeoutMs,
    WorkspaceStatus,
    WorktreeName,
)
from mb_workflow.d_lib.logging import Activity
from mb_workflow.d_lib.models import Model
from mb_workflow.d_lib.saga import Saga, SagaStep

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.claims import ClaimRegistry
    from mb_workflow.b_core.c_secondary_ports.status import WorkspaceStatusStore
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import TicketTracker
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import WorkspaceManager
    from mb_workflow.b_core.d_domain_model.config import ClaimSettings, WorkspaceSettings
    from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
    from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses
    from mb_workflow.b_core.d_domain_model.workspace import OpenedWorktree

logger = logging.getLogger(__name__)


class PromptUndeliveredError(Exception):
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


class WorktreeStep(SagaStep):
    def __init__(self, manager: WorkspaceManager, creation: WorktreeCreation) -> None:
        self._manager = manager
        self._creation = creation
        self._opened: OpenedWorktree | None = None

    @override
    def apply(self) -> Result[None, Exception]:
        try:
            with Activity(f"Creating worktree {self._creation.name.root}").logged(logger):
                self._opened = self._manager.create_for_issue(
                    self._creation.project,
                    self._creation.name,
                    self._creation.ticket,
                    self._creation.agent,
                    self._creation.status,
                    activate=self._creation.activate,
                )
        except WorkspaceManagerError as error:
            return Err(error)
        return Ok(None)

    @override
    def revert(self) -> Result[None, Exception]:
        if self._opened is None:
            return Ok(None)
        try:
            with Activity(f"Removing worktree {self._creation.name.root}").logged(logger):
                self._manager.remove(self._opened.worktree.path)
        except WorkspaceManagerError as error:
            return Err(error)
        return Ok(None)

    def opened(self) -> Result[OpenedWorktree, WorkspaceManagerError]:
        if self._opened is None:
            return Err(
                WorkspaceManagerError(f"Worktree {self._creation.name.root} was not created.")
            )
        return Ok(self._opened)


class StartRequest(Model):
    ticket: IssueIdentifier
    submit: Submit
    idle_timeout: TimeoutMs
    host: HostName
    take_over: TakeOver
    activate: Activate
    # The state to put a ticket without a flow label in; None leaves the flow label to decide.
    state: StateName | None

    @staticmethod
    def fake() -> StartRequest:
        return StartRequest(
            ticket=IssueIdentifier.fake(),
            submit=Submit.fake(),
            idle_timeout=TimeoutMs.fake(),
            host=HostName.fake(),
            take_over=TakeOver.fake(),
            activate=Activate.fake(),
            state=None,
        )

    def prompt_for(self, action: Skill | AwaitingHuman) -> TerminalText | None:
        if isinstance(action, AwaitingHuman):
            return None
        return TerminalText(f"{action.root} {self.ticket.root}")

    def state_given(self, labelled_state: StateName | None) -> StateName:
        if labelled_state is not None:
            if self.state is not None:
                raise FlowError(
                    f"{self.ticket.root} is already in {labelled_state.root};"
                    " move it with `mw flow` instead of --state."
                )
            return labelled_state
        startable = TicketStart.startable_states()
        if self.state is None:
            listed = ", ".join(state.root for state in startable.root)
            raise FlowError(
                f"{self.ticket.root} carries no flow label, so it is not in the flow."
                f" Pass --state with one of {listed}."
            )
        return startable.named_ignoring_case(self.state).unwrap()


class TicketStart:
    @staticmethod
    def start_ticket(
        *,
        manager: WorkspaceManager,
        tracker: TicketTracker,
        claims: ClaimRegistry,
        board: WorkspaceStatusStore,
        workspace: WorkspaceSettings,
        claim_settings: ClaimSettings,
        flow_labels: FlowLabels,
        statuses: TicketStatuses,
        request: StartRequest,
    ) -> None:
        with Activity(f"Reading {request.ticket.root}").logged(logger):
            detail = tracker.read_issue_detail(request.ticket)
        labelled_state = state_of(WorkflowChart, flow_labels, detail.issue.grouped)
        state = request.state_given(labelled_state)
        prompt = request.prompt_for(TicketStart.action_in(request.ticket, state))
        Claiming.require_claim_label(tracker, claim_settings.label)

        # Put an unlabelled ticket in the flow before claiming it, so a failed write leaves no claim behind.
        status = detail.issue.status
        if labelled_state is None:
            with Activity(f"Putting {request.ticket.root} in {state.root}").logged(logger):
                put_in_state(tracker, request.ticket, flow_labels, statuses, state)
            status = statuses.of(state)

        name = WorktreeName.of_issue(request.ticket)
        creation = WorktreeStep(
            manager,
            WorktreeCreation(
                project=workspace.orca_project,
                name=name,
                ticket=request.ticket,
                agent=None if prompt is None else AgentName.claude(),
                status=board.status_for(state),
                activate=request.activate,
            ),
        )
        taking = TicketTaking.steps(
            claims=claims,
            tracker=tracker,
            workspace=workspace,
            claim_settings=claim_settings,
            request=ClaimRequest(
                ticket=request.ticket,
                status=status,
                holder=ClaimHolder(host=request.host, worktree=name),
                take_over=request.take_over,
            ),
            previous=detail.assignee,
        )
        Saga.run((*taking, creation)).unwrap()
        opened = creation.opened().unwrap()

        logger.info("Created worktree %s.", opened.worktree.path.root)
        with Activity(f"Naming worktree {name.root}").logged(logger):
            set_display_name_or_warn(
                manager, opened.worktree.path, DisplayName.of_issue(detail.title)
            )

        if prompt is not None:
            TicketStart.send_prompt(manager, opened, prompt, request.idle_timeout, request.submit)

    @staticmethod
    def startable_states() -> AcceptedStates:
        return AcceptedStates(
            tuple(
                state
                for state in AcceptedStates.of_chart(WorkflowChart).root
                if not isinstance(next_action(WorkflowChart, state), Finished)
            )
        )

    @staticmethod
    def action_in(ticket: IssueIdentifier, state: StateName) -> Skill | AwaitingHuman:
        action = next_action(WorkflowChart, state)
        if isinstance(action, Finished):
            raise FlowError(f"The ticket is {state.root}, so there is no work left in it.")
        if isinstance(action, AwaitingHuman):
            logger.warning(
                "%s is in %s, which waits for a human, so no prompt is typed.",
                ticket.root,
                state.root,
            )
        else:
            logger.info(
                "%s is in %s, so the next step is %s.", ticket.root, state.root, action.root
            )
        return action

    @staticmethod
    def send_prompt(
        manager: WorkspaceManager,
        opened: OpenedWorktree,
        prompt: TerminalText,
        idle_timeout: TimeoutMs,
        submit: Submit,
    ) -> None:
        if opened.terminal is None:
            raise PromptUndeliveredError("No agent terminal handle returned; prompt not typed.")

        try:
            with Activity("Waiting for the agent terminal to go idle").logged(logger):
                manager.wait_for_idle(opened.terminal, idle_timeout)
        except WorkspaceManagerError:
            logger.warning("Agent terminal never went idle; typing the prompt anyway.")

        with Activity(f"{'Submitting' if submit.root else 'Typing'} {prompt.root}").logged(logger):
            manager.send_text(opened.terminal, prompt, submit)
