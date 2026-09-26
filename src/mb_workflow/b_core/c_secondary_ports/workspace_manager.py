from typing import TYPE_CHECKING, Protocol, override

from mb_workflow.b_core.d_domain_model.workspace import (
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
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
    from mb_workflow.b_core.d_domain_model.pull_request import PrNumber, PrTitle
    from mb_workflow.b_core.d_domain_model.workspace import (
        AgentName,
        TerminalText,
        TimeoutMs,
        WorkspaceStatus,
    )


class WorkspaceManagerError(Exception):
    pass


class WorkspaceManager(Protocol):
    def current(self) -> Worktree: ...

    def worktrees(self) -> Worktrees: ...

    def create_for_review(
        self, repo: RepoId, pr: PrNumber, title: PrTitle, status: WorkspaceStatus
    ) -> Worktree: ...

    def create_for_issue(
        self,
        project: ProjectSelector,
        name: WorktreeName,
        issue: IssueIdentifier | None,
        agent: AgentName | None,
    ) -> OpenedWorktree: ...

    def remove(self, path: WorktreePath) -> None: ...

    def set_status(self, path: WorktreePath, status: WorkspaceStatus) -> None: ...

    def wait_for_idle(self, terminal: TerminalHandle, timeout: TimeoutMs) -> None: ...

    def send_text(self, terminal: TerminalHandle, text: TerminalText) -> None: ...


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
        self._terminals: dict[TerminalHandle, tuple[TerminalText, ...]] = {}

    @override
    def current(self) -> Worktree:
        return self._at(self._here)

    @override
    def worktrees(self) -> Worktrees:
        return self._worktrees

    @override
    def create_for_review(
        self, repo: RepoId, pr: PrNumber, title: PrTitle, status: WorkspaceStatus
    ) -> Worktree:
        worktree = Worktree.bare(repo, self._free(repo, WorktreeName.of(pr))).model_copy(
            update={"pull_request": pr, "status": self._column(status)}
        )
        self._worktrees = Worktrees((*self._worktrees.root, worktree))
        return worktree

    @override
    def create_for_issue(
        self,
        project: ProjectSelector,
        name: WorktreeName,
        issue: IssueIdentifier | None,
        agent: AgentName | None,
    ) -> OpenedWorktree:
        if project != self._project:
            raise WorkspaceManagerError(f"No project is selected by {project.root}.")
        worktree = Worktree.bare(self._repo, self._free(self._repo, name)).model_copy(
            update={"issue": issue}
        )
        self._worktrees = Worktrees((*self._worktrees.root, worktree))
        if agent is None:
            return OpenedWorktree(worktree=worktree, terminal=None)
        terminal = TerminalHandle(f"terminal-{len(self._terminals) + 1}")
        self._terminals[terminal] = ()
        return OpenedWorktree(worktree=worktree, terminal=terminal)

    @override
    def remove(self, path: WorktreePath) -> None:
        _ = self._at(path)
        self._worktrees = self._worktrees.without(path)

    @override
    def set_status(self, path: WorktreePath, status: WorkspaceStatus) -> None:
        moved = self._at(path).model_copy(update={"status": self._column(status)})
        self._worktrees = Worktrees(
            tuple(moved if w.path.same_as(path).root else w for w in self._worktrees.root)
        )

    @override
    def wait_for_idle(self, terminal: TerminalHandle, timeout: TimeoutMs) -> None:
        _ = self.typed(terminal)

    @override
    def send_text(self, terminal: TerminalHandle, text: TerminalText) -> None:
        self._terminals[terminal] = (*self.typed(terminal), text)

    def typed(self, terminal: TerminalHandle) -> tuple[TerminalText, ...]:
        typed = self._terminals.get(terminal)
        if typed is None:
            raise WorkspaceManagerError(f"No terminal is handled as {terminal.root}.")
        return typed

    def _free(self, repo: RepoId, name: WorktreeName) -> WorktreePath:
        taken = Worktrees(tuple(w for w in self._worktrees.root if w.repo == repo))
        path = self._here.sibling(name)
        suffix = 2
        while taken.at(path) is not None:
            path = self._here.sibling(WorktreeName(f"{name.root}-{suffix}"))
            suffix += 1
        return path

    def _column(self, status: WorkspaceStatus) -> WorkspaceStatus:
        if status not in self._columns.root:
            raise WorkspaceManagerError(f"The board has no column {status.root}.")
        return status

    def _at(self, path: WorktreePath) -> Worktree:
        worktree = self._worktrees.at(path)
        if worktree is None:
            raise WorkspaceManagerError(f"No worktree is at {path.root}.")
        return worktree
