import logging
from pathlib import Path

from mb_workflow.git import Ref
from mb_workflow.github import PrNumber, PullRequest
from mb_workflow.models import Payload, Value
from mb_workflow.shell import Command, CommandOutput, ExistingDirectory, Shell

logger = logging.getLogger(__name__)


class OrcaError(Exception):
    pass


class RepoId(Value[str]):
    @staticmethod
    def fake() -> RepoId:
        return RepoId("ed089d5b-6f96-45d2-ad3a-c2131bb3be91")


class WorktreeName(Value[str]):
    @staticmethod
    def fake() -> WorktreeName:
        return WorktreeName(f"pr-{PrNumber.fake().root}")

    @staticmethod
    def of(pr: PrNumber) -> WorktreeName:
        return WorktreeName(f"pr-{pr.root}")


class WorktreeComment(Value[str]):
    @staticmethod
    def fake() -> WorktreeComment:
        return WorktreeComment.of(PullRequest.fake())

    @staticmethod
    def of(pr: PullRequest) -> WorktreeComment:
        return WorktreeComment(f"PR #{pr.number.root} — {pr.title.root}")


class WorkspaceStatus(Value[str]):
    @staticmethod
    def fake() -> WorkspaceStatus:
        return WorkspaceStatus("Me reviewing others")


class ErrorMessage(Value[str]):
    @staticmethod
    def fake() -> ErrorMessage:
        return ErrorMessage("repo_not_found")


class WorktreePath(Value[Path]):
    @staticmethod
    def fake() -> WorktreePath:
        return WorktreePath(Path("/Users/me/orca/workspaces/mb-workflow/pr-1234"))

    def existing(self) -> ExistingDirectory:
        return ExistingDirectory(self.root)


class EnvelopeError(Payload):
    message: ErrorMessage

    @staticmethod
    def fake() -> EnvelopeError:
        return EnvelopeError(message=ErrorMessage.fake())


class Succeeded(Value[bool]):
    @staticmethod
    def fake() -> Succeeded:
        return Succeeded(True)


class Envelope[T](Payload):
    ok: Succeeded
    result: T | None = None
    error: EnvelopeError | None = None

    def unwrap(self) -> T:
        if self.result is None or not self.ok.root:
            raise OrcaError(
                self.error.message.root if self.error is not None else "orca returned no result"
            )
        return self.result


class Worktree(Payload):
    repo_id: RepoId
    path: WorktreePath
    branch: Ref | None = None
    linked_issue: PrNumber | None = None

    @staticmethod
    def fake() -> Worktree:
        return Worktree(
            repo_id=RepoId.fake(),
            path=WorktreePath.fake(),
            branch=Ref.fake(),
            linked_issue=PrNumber.fake(),
        )


class WorktreeList(Payload):
    worktrees: tuple[Worktree, ...]

    @staticmethod
    def fake() -> WorktreeList:
        return WorktreeList(worktrees=(Worktree.fake(),))


class Acknowledgement(Payload):
    @staticmethod
    def fake() -> Acknowledgement:
        return Acknowledgement()


class CreatedWorktree(Payload):
    worktree: Worktree

    @staticmethod
    def fake() -> CreatedWorktree:
        return CreatedWorktree(worktree=Worktree.fake())


class Worktrees(Value[tuple[Worktree, ...]]):
    @staticmethod
    def fake() -> Worktrees:
        return Worktrees((Worktree.fake(),))

    @staticmethod
    def parse(output: CommandOutput) -> Worktrees:
        envelope = Envelope[WorktreeList].model_validate_json(output.root)
        return Worktrees(envelope.unwrap().worktrees)

    def repo_id_at(self, directory: ExistingDirectory) -> RepoId:
        wanted = directory.root.resolve()
        for worktree in self.root:
            if worktree.path.root.resolve() == wanted:
                return worktree.repo_id
        raise OrcaError(f"{wanted} is not an Orca-managed worktree")


def created_path(output: CommandOutput) -> ExistingDirectory:
    envelope = Envelope[CreatedWorktree].model_validate_json(output.root)
    return envelope.unwrap().worktree.path.existing()


def acknowledged(output: CommandOutput) -> Acknowledgement:
    return Envelope[Acknowledgement].model_validate_json(output.root).unwrap()


class Orca:
    def __init__(self, shell: Shell) -> None:
        self._shell = shell
        _ = shell.run(Command(("orca", "--version")))

    def where(self) -> ExistingDirectory:
        return self._shell.cwd()

    def worktrees(self) -> Worktrees:
        return Worktrees.parse(self._shell.run(Command(("orca", "worktree", "list", "--json"))))

    def create_worktree(self, repo: RepoId, pr: PullRequest) -> ExistingDirectory:
        return created_path(
            self._shell.run(
                Command(
                    (
                        "orca",
                        "worktree",
                        "create",
                        "--repo",
                        f"id:{repo.root}",
                        "--name",
                        WorktreeName.of(pr.number).root,
                        "--no-parent",
                        "--issue",
                        str(pr.number.root),
                        "--comment",
                        WorktreeComment.of(pr).root,
                        "--json",
                    )
                )
            )
        )

    def set_status(self, pr: PrNumber, status: WorkspaceStatus) -> None:
        _ = acknowledged(
            self._shell.run(
                Command(
                    (
                        "orca",
                        "worktree",
                        "set",
                        "--worktree",
                        f"issue:{pr.root}",
                        "--workspace-status",
                        status.root,
                        "--json",
                    )
                )
            )
        )
