import logging
from typing import TYPE_CHECKING, Protocol, override

from safe_result import Err, Ok, Result

from mb_workflow.b_core.d_domain_model.workspace import (
    DisplayName,
    OpenedWorktree,
    ProjectSelector,
    RepoId,
    TerminalHandle,
    WorkspaceStatuses,
    Worktree,
    WorktreeName,
    WorktreePath,
    Worktrees,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
    from mb_workflow.b_core.d_domain_model.pull_request import PrNumber
    from mb_workflow.b_core.d_domain_model.workspace import (
        Activate,
        AgentName,
        Submit,
        TerminalText,
        TimeoutMs,
        WorkspaceStatus,
    )

logger = logging.getLogger(__name__)


class WorkspaceManagerError(Exception):
    pass


class WorkspaceManager(Protocol):
    def current(self) -> Result[Worktree, WorkspaceManagerError]: ...

    def worktrees(self) -> Result[Worktrees, WorkspaceManagerError]: ...

    def create_for_review(
        self, repo: RepoId, pr: PrNumber, status: WorkspaceStatus, agent: AgentName | None
    ) -> Result[OpenedWorktree, WorkspaceManagerError]: ...

    def create_for_issue(
        self,
        project: ProjectSelector,
        name: WorktreeName,
        issue: IssueIdentifier | None,
        agent: AgentName | None,
        status: WorkspaceStatus | None,
        *,
        activate: Activate,
    ) -> Result[OpenedWorktree, WorkspaceManagerError]: ...

    def remove(self, path: WorktreePath) -> Result[None, WorkspaceManagerError]: ...

    def set_status(
        self, path: WorktreePath, status: WorkspaceStatus
    ) -> Result[None, WorkspaceManagerError]: ...

    def set_display_name(
        self, path: WorktreePath, name: DisplayName
    ) -> Result[None, WorkspaceManagerError]: ...

    def set_linked_issue(
        self, path: WorktreePath, issue: IssueIdentifier
    ) -> Result[None, WorkspaceManagerError]: ...

    def wait_for_idle(
        self, terminal: TerminalHandle, timeout: TimeoutMs
    ) -> Result[None, WorkspaceManagerError]: ...

    def send_text(
        self, terminal: TerminalHandle, text: TerminalText, submit: Submit
    ) -> Result[None, WorkspaceManagerError]: ...


class FakeWorkspaceManager(WorkspaceManager):
    def __init__(
        self,
        worktrees: Worktrees,
        here: WorktreePath,
        columns: WorkspaceStatuses = WorkspaceStatuses.fake(),
        project: ProjectSelector = ProjectSelector.fake(),
        repo: RepoId = RepoId.fake(),
    ) -> None:
        self._worktrees = worktrees
        self._here = here
        self._columns = columns
        self._project = project
        self._repo = repo
        self._terminals: dict[TerminalHandle, tuple[tuple[TerminalText, Submit], ...]] = {}
        self._activated: tuple[WorktreePath, ...] = ()

    @override
    def current(self) -> Result[Worktree, WorkspaceManagerError]:
        return self._at(self._here)

    @override
    def worktrees(self) -> Result[Worktrees, WorkspaceManagerError]:
        return Ok(self._worktrees)

    @override
    def create_for_review(
        self, repo: RepoId, pr: PrNumber, status: WorkspaceStatus, agent: AgentName | None
    ) -> Result[OpenedWorktree, WorkspaceManagerError]:
        match self._column(status):
            case Ok(column):
                worktree = self._add(
                    Worktree.bare(repo, self._unused_path(WorktreeName.of(pr))).model_copy(
                        update={"pull_request": pr, "status": column}
                    )
                )
                return Ok(self._opened(worktree, agent))
            case Err() as refused:
                return refused

    @override
    def create_for_issue(
        self,
        project: ProjectSelector,
        name: WorktreeName,
        issue: IssueIdentifier | None,
        agent: AgentName | None,
        status: WorkspaceStatus | None,
        *,
        activate: Activate,
    ) -> Result[OpenedWorktree, WorkspaceManagerError]:
        if project != self._project:
            return Err(WorkspaceManagerError(f"No project is selected by {project.root}."))
        column: WorkspaceStatus | None = None
        if status is not None:
            match self._column(status):
                case Ok(listed):
                    column = listed
                case Err() as refused:
                    return refused
        worktree = self._add(
            Worktree.bare(self._repo, self._unused_path(name)).model_copy(
                update={"issue": issue, "status": column}
            )
        )
        if activate.root:
            self._activated = (*self._activated, worktree.path)
        return Ok(self._opened(worktree, agent))

    @override
    def remove(self, path: WorktreePath) -> Result[None, WorkspaceManagerError]:
        match self._at(path):
            case Ok():
                self._worktrees = self._worktrees.without(path)
                return Ok(None)
            case Err() as missing:
                return missing

    @override
    def set_status(
        self, path: WorktreePath, status: WorkspaceStatus
    ) -> Result[None, WorkspaceManagerError]:
        match self._column(status):
            case Ok(column):
                return self._update(path, lambda w: w.model_copy(update={"status": column}))
            case Err() as refused:
                return refused

    @override
    def set_display_name(
        self, path: WorktreePath, name: DisplayName
    ) -> Result[None, WorkspaceManagerError]:
        return self._update(path, lambda w: w.model_copy(update={"display_name": name}))

    @override
    def set_linked_issue(
        self, path: WorktreePath, issue: IssueIdentifier
    ) -> Result[None, WorkspaceManagerError]:
        return self._update(path, lambda w: w.model_copy(update={"issue": issue}))

    @override
    def wait_for_idle(
        self, terminal: TerminalHandle, timeout: TimeoutMs
    ) -> Result[None, WorkspaceManagerError]:
        match self._typed_into(terminal):
            case Ok():
                return Ok(None)
            case Err() as unknown:
                return unknown

    @override
    def send_text(
        self, terminal: TerminalHandle, text: TerminalText, submit: Submit
    ) -> Result[None, WorkspaceManagerError]:
        match self._typed_into(terminal):
            case Ok(typed):
                self._terminals[terminal] = (*typed, (text, submit))
                return Ok(None)
            case Err() as unknown:
                return unknown

    def activated(self) -> tuple[WorktreePath, ...]:
        return self._activated

    def typed_texts(self) -> tuple[TerminalText, ...]:
        return tuple(text for typed in self._terminals.values() for text, _ in typed)

    def submitted_texts(self) -> tuple[TerminalText, ...]:
        return tuple(
            text for typed in self._terminals.values() for text, submit in typed if submit.root
        )

    def _opened(self, worktree: Worktree, agent: AgentName | None) -> OpenedWorktree:
        if agent is None:
            return OpenedWorktree(worktree=worktree, terminal=None)
        terminal = TerminalHandle(f"terminal-{len(self._terminals) + 1}")
        self._terminals[terminal] = ()
        return OpenedWorktree(worktree=worktree, terminal=terminal)

    def _typed_into(
        self, terminal: TerminalHandle
    ) -> Result[tuple[tuple[TerminalText, Submit], ...], WorkspaceManagerError]:
        typed = self._terminals.get(terminal)
        if typed is None:
            return Err(WorkspaceManagerError(f"No terminal is handled as {terminal.root}."))
        return Ok(typed)

    def _update(
        self, path: WorktreePath, change: Callable[[Worktree], Worktree]
    ) -> Result[None, WorkspaceManagerError]:
        match self._at(path):
            case Ok(worktree):
                changed = change(worktree)
                self._worktrees = Worktrees(
                    tuple(
                        changed if w.path.same_as(changed.path).root else w
                        for w in self._worktrees.root
                    )
                )
                return Ok(None)
            case Err() as missing:
                return missing

    def _add(self, worktree: Worktree) -> Worktree:
        self._worktrees = Worktrees((*self._worktrees.root, worktree))
        return worktree

    def _unused_path(self, name: WorktreeName) -> WorktreePath:
        path = self._here.sibling(name)
        suffix = 2
        while self._worktrees.at(path) is not None:
            path = self._here.sibling(WorktreeName(f"{name.root}-{suffix}"))
            suffix += 1
        return path

    def _column(self, status: WorkspaceStatus) -> Result[WorkspaceStatus, WorkspaceManagerError]:
        if status not in self._columns.root:
            return Err(WorkspaceManagerError(f"The board has no column {status.root}."))
        return Ok(status)

    def _at(self, path: WorktreePath) -> Result[Worktree, WorkspaceManagerError]:
        worktree = self._worktrees.at(path)
        if worktree is None:
            return Err(WorkspaceManagerError(f"No worktree is at {path.root}."))
        return Ok(worktree)


class DisplayNameRefusingWorkspaceManager(FakeWorkspaceManager):
    @override
    def set_display_name(
        self, path: WorktreePath, name: DisplayName
    ) -> Result[None, WorkspaceManagerError]:
        return Err(WorkspaceManagerError(f"Orca refused the display name {name.root}."))


class LinkRefusingWorkspaceManager(FakeWorkspaceManager):
    @override
    def set_linked_issue(
        self, path: WorktreePath, issue: IssueIdentifier
    ) -> Result[None, WorkspaceManagerError]:
        return Err(WorkspaceManagerError(f"Orca refused to link {issue.root}."))


class WorkspaceNaming:
    @staticmethod
    def set_display_name_or_warn(
        manager: WorkspaceManager, path: WorktreePath, name: DisplayName
    ) -> None:
        match manager.set_display_name(path, name):
            case Ok():
                pass
            case Err(error):
                logger.warning("Could not name %s %s: %s", path.root, name.root, error)
