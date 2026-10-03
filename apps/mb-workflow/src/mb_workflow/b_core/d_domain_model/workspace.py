from pathlib import Path

from pydantic import JsonValue, model_validator

from mb_workflow.b_core.d_domain_model.git import Ref
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier, IssueTitle
from mb_workflow.b_core.d_domain_model.pull_request import PrNumber, PrTitle
from mb_workflow.d_lib.models import Model, Value


class RepoId(Value[str]):
    @staticmethod
    def fake() -> RepoId:
        return RepoId("ed089d5b-6f96-45d2-ad3a-c2131bb3be91")


class ProjectSelector(Value[str]):
    @staticmethod
    def fake() -> ProjectSelector:
        return ProjectSelector("github:flowbasedk/flowbase")

    # Orca stores project IDs in lowercase and matches them case-sensitively.
    @model_validator(mode="before")
    @classmethod
    def lowercased(cls, data: JsonValue) -> JsonValue:
        return data.lower() if isinstance(data, str) else data


class WorktreeName(Value[str]):
    @staticmethod
    def fake() -> WorktreeName:
        return WorktreeName(f"pr-{PrNumber.fake().root}")

    @staticmethod
    def of(pr: PrNumber) -> WorktreeName:
        return WorktreeName(f"pr-{pr.root}")

    @staticmethod
    def of_issue(issue: IssueIdentifier) -> WorktreeName:
        return WorktreeName(issue.root)


class DisplayName(Value[str]):
    @staticmethod
    def fake() -> DisplayName:
        return DisplayName.of_issue(IssueTitle.fake())

    @staticmethod
    def of_issue(title: IssueTitle) -> DisplayName:
        return DisplayName(title.root)

    @staticmethod
    def of_pr(title: PrTitle) -> DisplayName:
        return DisplayName(title.root)


class WorktreePath(Value[Path]):
    @staticmethod
    def fake() -> WorktreePath:
        return WorktreePath(Path("/Users/me/orca/workspaces/mb-workflow/pr-1234"))

    def sibling(self, name: WorktreeName) -> WorktreePath:
        return WorktreePath(self.root.parent / name.root)

    def name(self) -> WorktreeName:
        return WorktreeName(self.root.name)

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


class Submit(Value[bool]):
    @staticmethod
    def fake() -> Submit:
        return Submit(False)


class Activate(Value[bool]):
    @staticmethod
    def fake() -> Activate:
        return Activate(True)


class TimeoutMs(Value[int]):
    @staticmethod
    def fake() -> TimeoutMs:
        return TimeoutMs(60000)


class UnlinkedWorktreeError(Exception):
    pass


class Worktree(Model):
    repo: RepoId
    path: WorktreePath
    branch: Ref | None
    pull_request: PrNumber | None
    issue: IssueIdentifier | None
    status: WorkspaceStatus | None
    display_name: DisplayName | None

    @staticmethod
    def fake() -> Worktree:
        return Worktree(
            repo=RepoId.fake(),
            path=WorktreePath.fake(),
            branch=Ref.fake(),
            pull_request=PrNumber.fake(),
            issue=IssueIdentifier.fake(),
            status=WorkspaceStatus.fake(),
            display_name=DisplayName.fake(),
        )

    def linked_issue(self) -> IssueIdentifier:
        if self.issue is None:
            raise UnlinkedWorktreeError(
                f"{self.path.root} has no linked Linear issue. Link one with `mw link <ticket>`."
            )
        return self.issue

    @staticmethod
    def bare(repo: RepoId, path: WorktreePath) -> Worktree:
        return Worktree(
            repo=repo,
            path=path,
            branch=None,
            pull_request=None,
            issue=None,
            status=None,
            display_name=None,
        )


class Worktrees(Value[tuple[Worktree, ...]]):
    @staticmethod
    def fake() -> Worktrees:
        return Worktrees((Worktree.fake(),))

    def at(self, path: WorktreePath) -> Worktree | None:
        return next((worktree for worktree in self.root if worktree.path.same_as(path).root), None)

    def named(self, name: WorktreeName) -> Worktree | None:
        return next((worktree for worktree in self.root if worktree.path.name() == name), None)

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
