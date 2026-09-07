import logging
from subprocess import CalledProcessError

from mb_workflow.models import Value
from mb_workflow.shell import Command, Shell

logger = logging.getLogger(__name__)


class IssueIdentifier(Value[str]):
    @staticmethod
    def fake() -> IssueIdentifier:
        return IssueIdentifier("E-4289")


class BranchSlug(Value[str]):
    @staticmethod
    def fake() -> BranchSlug:
        return BranchSlug(f"mab/{IssueIdentifier.fake().root.lower()}-feat-add-widget")


class Assignee(Value[str]):
    @staticmethod
    def fake() -> Assignee:
        return Assignee("mab@flowbase.io")


class AssignmentFailure(Value[str]):
    @staticmethod
    def fake() -> AssignmentFailure:
        return AssignmentFailure("linearis is not installed or not on PATH")


class Linear:
    def __init__(self, shell: Shell) -> None:
        self._shell = shell

    def assign(self, issue: IssueIdentifier, assignee: Assignee) -> AssignmentFailure | None:
        try:
            _ = self._shell.run(
                Command(("linearis", "issues", "update", issue.root, "--assignee", assignee.root))
            )
        except (CalledProcessError, FileNotFoundError) as error:
            return AssignmentFailure(str(error))
        return None
