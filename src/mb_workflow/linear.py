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


class Linear:
    def __init__(self, shell: Shell) -> None:
        self._shell = shell

    # Assignment is a convenience, not the point of opening a workspace, so never fail the run over it.
    def assign(self, issue: IssueIdentifier, assignee: Assignee) -> None:
        try:
            _ = self._shell.run(
                Command(("linearis", "issues", "update", issue.root, "--assignee", assignee.root))
            )
        except (CalledProcessError, FileNotFoundError) as error:
            logger.warning("Could not assign %s to %s: %s", issue.root, assignee.root, error)
