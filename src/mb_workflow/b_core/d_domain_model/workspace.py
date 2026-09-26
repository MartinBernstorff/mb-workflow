import re
from pathlib import Path

from mb_workflow.b_core.d_domain_model.git import Ref
from mb_workflow.b_core.d_domain_model.issue import BranchSlug, IssueIdentifier
from mb_workflow.b_core.d_domain_model.pull_request import PrNumber
from mb_workflow.d_lib.models import Model, Value


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


class WorktreePath(Value[Path]):
    @staticmethod
    def fake() -> WorktreePath:
        return WorktreePath(Path("/Users/me/orca/workspaces/mb-workflow/pr-1234"))

    def sibling(self, name: WorktreeName) -> WorktreePath:
        return WorktreePath(self.root.parent / name.root)

    def same_as(self, other: WorktreePath) -> SamePath:
        return SamePath(self.root.resolve() == other.root.resolve())


class SamePath(Value[bool]):
    @staticmethod
    def fake() -> SamePath:
        return SamePath(True)


# A board column's id, which stays put when the column is relabelled.
class WorkspaceStatus(Value[str]):
    @staticmethod
    def fake() -> WorkspaceStatus:
        return WorkspaceStatus("status-8")


class WorkspaceStatuses(Value[tuple[WorkspaceStatus, ...]]):
    @staticmethod
    def fake() -> WorkspaceStatuses:
        return WorkspaceStatuses((WorkspaceStatus.fake(), WorkspaceStatus("status-5")))


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
    branch: Ref | None
    pull_request: PrNumber | None
    issue: IssueIdentifier | None
    status: WorkspaceStatus | None

    @staticmethod
    def fake() -> Worktree:
        return Worktree(
            repo=RepoId.fake(),
            path=WorktreePath.fake(),
            branch=Ref.fake(),
            pull_request=PrNumber.fake(),
            issue=IssueIdentifier.fake(),
            status=WorkspaceStatus.fake(),
        )

    @staticmethod
    def bare(repo: RepoId, path: WorktreePath) -> Worktree:
        return Worktree(
            repo=repo, path=path, branch=None, pull_request=None, issue=None, status=None
        )


class Worktrees(Value[tuple[Worktree, ...]]):
    @staticmethod
    def fake() -> Worktrees:
        return Worktrees((Worktree.fake(),))

    def at(self, path: WorktreePath) -> Worktree | None:
        return next((worktree for worktree in self.root if worktree.path.same_as(path).root), None)

    def without(self, path: WorktreePath) -> Worktrees:
        return Worktrees(
            tuple(worktree for worktree in self.root if not worktree.path.same_as(path).root)
        )


class OpenedWorktree(Model):
    worktree: Worktree
    terminal: TerminalHandle | None

    @staticmethod
    def fake() -> OpenedWorktree:
        return OpenedWorktree(worktree=Worktree.fake(), terminal=TerminalHandle.fake())
