import re
from pathlib import Path

from mb_workflow.b_core.d_domain_model.directory import ExistingDirectory
from mb_workflow.b_core.d_domain_model.git import Ref
from mb_workflow.b_core.d_domain_model.issue import BranchSlug, IssueIdentifier
from mb_workflow.b_core.d_domain_model.pull_request import PrNumber
from mb_workflow.d_lib.models import Model, Value


class WorkspaceError(Exception):
    pass


class RepoId(Value[str]):
    @staticmethod
    def fake() -> RepoId:
        return RepoId("ed089d5b-6f96-45d2-ad3a-c2131bb3be91")


class ProjectSelector(Value[str]):
    @staticmethod
    def fake() -> ProjectSelector:
        return ProjectSelector("github:flowbasedk/flowbase")


class WorktreeName(Value[str]):
    @staticmethod
    def fake() -> WorktreeName:
        return WorktreeName(f"pr-{PrNumber.fake().root}")

    @staticmethod
    def of(pr: PrNumber) -> WorktreeName:
        return WorktreeName(f"pr-{pr.root}")

    @staticmethod
    def of_branch(branch: BranchSlug, issue: IssueIdentifier | None) -> WorktreeName:
        slug = branch.root or (issue.root if issue is not None else "linear-workspace")
        # Orca prefixes the branch with the git user, so hand it the unprefixed slug.
        name = slug.split("/", 1)[-1]
        # Linear prefixes the slug with the issue identifier ("e-4289-..."), which orca shows on its own.
        name = re.sub(r"^[A-Za-z]+-\d+-", "", name)
        # Linear slugifies "fix(ci): ..." to "fixci-...", so drop the conventional-commit type and scope.
        name = re.sub(
            r"^(?:feat|fix|chore|refactor|revert|perf|docs|test|build|style|ci)[a-z]*-(?=.)",
            "",
            name,
        )
        return WorktreeName(name)


class WorkspaceStatus(Value[str]):
    @staticmethod
    def fake() -> WorkspaceStatus:
        return WorkspaceStatus("status-8")


class WorkspaceStatuses(Value[frozenset[WorkspaceStatus]]):
    @staticmethod
    def fake() -> WorkspaceStatuses:
        return WorkspaceStatuses(frozenset({WorkspaceStatus.fake()}))


class WorktreePath(Value[Path]):
    @staticmethod
    def fake() -> WorktreePath:
        return WorktreePath(Path("/Users/me/orca/workspaces/mb-workflow/pr-1234"))

    @staticmethod
    def of(directory: ExistingDirectory) -> WorktreePath:
        return WorktreePath(directory.root)

    def existing(self) -> ExistingDirectory:
        return ExistingDirectory(self.root)

    def resolved(self) -> WorktreePath:
        return WorktreePath(self.root.resolve())


class AgentName(Value[str]):
    @staticmethod
    def fake() -> AgentName:
        return AgentName.claude()

    @staticmethod
    def claude() -> AgentName:
        return AgentName("claude")


class TerminalHandle(Value[str]):
    @staticmethod
    def fake() -> TerminalHandle:
        return TerminalHandle("terminal-1")


class TerminalText(Value[str]):
    @staticmethod
    def fake() -> TerminalText:
        return TerminalText("Implement the issue.")


class TimeoutMs(Value[int]):
    @staticmethod
    def fake() -> TimeoutMs:
        return TimeoutMs(60000)


class Worktree(Model):
    repo: RepoId
    path: WorktreePath
    name: WorktreeName | None = None
    project: ProjectSelector | None = None
    branch: Ref | None = None
    pull_request: PrNumber | None = None
    issue: IssueIdentifier | None = None
    status: WorkspaceStatus | None = None

    @staticmethod
    def fake() -> Worktree:
        return Worktree(
            repo=RepoId.fake(),
            path=WorktreePath.fake(),
            name=WorktreeName.fake(),
            project=ProjectSelector.fake(),
            branch=Ref.fake(),
            pull_request=PrNumber.fake(),
            issue=IssueIdentifier.fake(),
            status=WorkspaceStatus.fake(),
        )


class OpenedWorktree(Model):
    worktree: Worktree
    terminal: TerminalHandle | None

    @staticmethod
    def fake() -> OpenedWorktree:
        return OpenedWorktree(worktree=Worktree.fake(), terminal=TerminalHandle.fake())


class Worktrees(Value[tuple[Worktree, ...]]):
    @staticmethod
    def fake() -> Worktrees:
        return Worktrees((Worktree.fake(),))

    def repo_id_at(self, directory: ExistingDirectory) -> RepoId:
        return self.at(WorktreePath.of(directory)).repo

    def at(self, path: WorktreePath) -> Worktree:
        for worktree in self.root:
            if worktree.path.resolved() == path.resolved():
                return worktree
        raise WorkspaceError(f"{path.resolved().root} is not a managed worktree")

    def in_repo(self, repo: RepoId) -> Worktrees:
        return Worktrees(tuple(w for w in self.root if w.repo == repo))

    def in_project(self, project: ProjectSelector) -> Worktrees:
        return Worktrees(tuple(w for w in self.root if w.project == project))

    def refuse_duplicate(self, name: WorktreeName) -> None:
        if any(w.name == name for w in self.root):
            raise WorkspaceError(f"A worktree named {name.root} already exists")

    def without(self, path: WorktreePath) -> Worktrees:
        return Worktrees(tuple(w for w in self.root if w.path.resolved() != path.resolved()))
