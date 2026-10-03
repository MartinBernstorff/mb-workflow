import logging
from typing import TYPE_CHECKING, Protocol, override

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
    def current(self) -> Worktree: ...

    def worktrees(self) -> Worktrees: ...

    def create_for_review(
        self, repo: RepoId, pr: PrNumber, status: WorkspaceStatus, agent: AgentName | None
    ) -> OpenedWorktree: ...

    def create_for_issue(
        self,
        project: ProjectSelector,
        name: WorktreeName,
        issue: IssueIdentifier | None,
        agent: AgentName | None,
        status: WorkspaceStatus | None,
        *,
        activate: Activate,
    ) -> OpenedWorktree: ...

    def remove(self, path: WorktreePath) -> None: ...

    def set_status(self, path: WorktreePath, status: WorkspaceStatus) -> None: ...

    def set_display_name(self, path: WorktreePath, name: DisplayName) -> None: ...

    def set_linked_issue(self, path: WorktreePath, issue: IssueIdentifier) -> None: ...

    def wait_for_idle(self, terminal: TerminalHandle, timeout: TimeoutMs) -> None: ...

    def send_text(self, terminal: TerminalHandle, text: TerminalText, submit: Submit) -> None: ...


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
    def current(self) -> Worktree:
        return self._at(self._here)

    @override
    def worktrees(self) -> Worktrees:
        return self._worktrees

    @override
    def create_for_review(
        self, repo: RepoId, pr: PrNumber, status: WorkspaceStatus, agent: AgentName | None
    ) -> OpenedWorktree:
        worktree = self._add(
            Worktree.bare(repo, self._unused_path(WorktreeName.of(pr))).model_copy(
                update={"pull_request": pr, "status": self._column(status)}
            )
        )
        return self._opened(worktree, agent)

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
    ) -> OpenedWorktree:
        if project != self._project:
            raise WorkspaceManagerError(f"No project is selected by {project.root}.")
        column = None if status is None else self._column(status)
        worktree = self._add(
            Worktree.bare(self._repo, self._unused_path(name)).model_copy(
                update={"issue": issue, "status": column}
            )
        )
        if activate.root:
            self._activated = (*self._activated, worktree.path)
        return self._opened(worktree, agent)

    @override
    def remove(self, path: WorktreePath) -> None:
        _ = self._at(path)
        self._worktrees = self._worktrees.without(path)

    @override
    def set_status(self, path: WorktreePath, status: WorkspaceStatus) -> None:
        self._replace(self._at(path).model_copy(update={"status": self._column(status)}))

    @override
    def set_display_name(self, path: WorktreePath, name: DisplayName) -> None:
        self._replace(self._at(path).model_copy(update={"display_name": name}))

    @override
    def set_linked_issue(self, path: WorktreePath, issue: IssueIdentifier) -> None:
        self._replace(self._at(path).model_copy(update={"issue": issue}))

    @override
    def wait_for_idle(self, terminal: TerminalHandle, timeout: TimeoutMs) -> None:
        _ = self._typed_into(terminal)

    @override
    def send_text(self, terminal: TerminalHandle, text: TerminalText, submit: Submit) -> None:
        self._terminals[terminal] = (*self._typed_into(terminal), (text, submit))

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

    def _typed_into(self, terminal: TerminalHandle) -> tuple[tuple[TerminalText, Submit], ...]:
        typed = self._terminals.get(terminal)
        if typed is None:
            raise WorkspaceManagerError(f"No terminal is handled as {terminal.root}.")
        return typed

    def _replace(self, changed: Worktree) -> None:
        self._worktrees = Worktrees(
            tuple(changed if w.path.same_as(changed.path).root else w for w in self._worktrees.root)
        )

    def _add(self, worktree: Worktree) -> Worktree:
        self._worktrees = Worktrees((*self._worktrees.root, worktree))
        return worktree

    # Orca keeps a taken name by suffixing the directory rather than refusing it.
    def _unused_path(self, name: WorktreeName) -> WorktreePath:
        path = self._here.sibling(name)
        suffix = 2
        while self._worktrees.at(path) is not None:
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


class DisplayNameRefusingWorkspaceManager(FakeWorkspaceManager):
    @override
    def set_display_name(self, path: WorktreePath, name: DisplayName) -> None:
        raise WorkspaceManagerError(f"Orca refused the display name {name.root}.")


class LinkRefusingWorkspaceManager(FakeWorkspaceManager):
    @override
    def set_linked_issue(self, path: WorktreePath, issue: IssueIdentifier) -> None:
        raise WorkspaceManagerError(f"Orca refused to link {issue.root}.")


class WorkspaceNaming:
    # The display name is cosmetic, so a refusal leaves the worktree under its directory name.
    @staticmethod
    def set_display_name_or_warn(
        manager: WorkspaceManager, path: WorktreePath, name: DisplayName
    ) -> None:
        try:
            manager.set_display_name(path, name)
        except WorkspaceManagerError as error:
            logger.warning("Could not name %s %s: %s", path.root, name.root, error)
