from typing import TYPE_CHECKING, Protocol

from mb_workflow.b_core.d_domain_model.workspace import (
    OpenedWorktree,
    TerminalHandle,
    WorkspaceError,
    Worktree,
    WorktreeName,
    WorktreePath,
    Worktrees,
)

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.directory import ExistingDirectory
    from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
    from mb_workflow.b_core.d_domain_model.pull_request import PrNumber, PrTitle
    from mb_workflow.b_core.d_domain_model.workspace import (
        AgentName,
        ProjectSelector,
        RepoId,
        TerminalText,
        TimeoutMs,
        WorkspaceStatus,
        WorkspaceStatuses,
    )


class WorkspaceManager(Protocol):
    def where(self) -> ExistingDirectory: ...

    def current(self) -> Worktree: ...

    def worktrees(self) -> Worktrees: ...

    def create_for_review(
        self, repo: RepoId, pr: PrNumber, title: PrTitle, status: WorkspaceStatus
    ) -> WorktreePath: ...

    def create_for_issue(
        self,
        project: ProjectSelector,
        name: WorktreeName,
        issue: IssueIdentifier | None,
        agent: AgentName | None,
    ) -> OpenedWorktree: ...

    def wait_for_idle(self, terminal: TerminalHandle, timeout: TimeoutMs) -> None: ...

    def send_text(self, terminal: TerminalHandle, text: TerminalText) -> None: ...

    def set_status(self, path: WorktreePath, status: WorkspaceStatus) -> None: ...

    def remove_worktree(self, path: WorktreePath) -> None: ...


class FakeWorkspaceManager:
    def __init__(
        self, here: ExistingDirectory, statuses: WorkspaceStatuses, worktrees: Worktrees
    ) -> None:
        self._here = here
        self._statuses = statuses
        self._worktrees = worktrees
        self._terminals: set[TerminalHandle] = set()

    def where(self) -> ExistingDirectory:
        return self._here

    def current(self) -> Worktree:
        return self._worktrees.at(WorktreePath.of(self._here))

    def worktrees(self) -> Worktrees:
        return self._worktrees

    def create_for_review(
        self, repo: RepoId, pr: PrNumber, title: PrTitle, status: WorkspaceStatus
    ) -> WorktreePath:
        del title
        self._refuse_unknown(status)
        name = WorktreeName.of(pr)
        self._worktrees.in_repo(repo).refuse_duplicate(name)
        worktree = Worktree(
            repo=repo, path=self._path_for(repo, name), name=name, pull_request=pr, status=status
        )
        self._worktrees = Worktrees((*self._worktrees.root, worktree))
        return worktree.path

    def create_for_issue(
        self,
        project: ProjectSelector,
        name: WorktreeName,
        issue: IssueIdentifier | None,
        agent: AgentName | None,
    ) -> OpenedWorktree:
        siblings = self._worktrees.in_project(project)
        if len(siblings.root) == 0:
            raise WorkspaceError(f"No repo is known for project {project.root}")
        siblings.refuse_duplicate(name)
        repo = siblings.root[0].repo
        worktree = Worktree(
            repo=repo,
            path=self._path_for(repo, name),
            name=name,
            project=project,
            issue=issue,
        )
        self._worktrees = Worktrees((*self._worktrees.root, worktree))
        terminal = TerminalHandle(f"terminal-{name.root}") if agent is not None else None
        if terminal is not None:
            self._terminals.add(terminal)
        return OpenedWorktree(worktree=worktree, terminal=terminal)

    def wait_for_idle(self, terminal: TerminalHandle, timeout: TimeoutMs) -> None:
        del timeout
        self._refuse_unknown_terminal(terminal)

    def send_text(self, terminal: TerminalHandle, text: TerminalText) -> None:
        del text
        self._refuse_unknown_terminal(terminal)

    def set_status(self, path: WorktreePath, status: WorkspaceStatus) -> None:
        self._refuse_unknown(status)
        moved = self._worktrees.at(path).model_copy(update={"status": status})
        self._worktrees = Worktrees((*self._worktrees.without(path).root, moved))

    def remove_worktree(self, path: WorktreePath) -> None:
        _ = self._worktrees.at(path)
        self._worktrees = self._worktrees.without(path)

    def _path_for(self, repo: RepoId, name: WorktreeName) -> WorktreePath:
        return WorktreePath(self._here.root.parent / repo.root / name.root)

    def _refuse_unknown(self, status: WorkspaceStatus) -> None:
        if status not in self._statuses.root:
            raise WorkspaceError(f"The board has no column for {status.root}")

    def _refuse_unknown_terminal(self, terminal: TerminalHandle) -> None:
        if terminal not in self._terminals:
            raise WorkspaceError(f"No terminal {terminal.root}")
