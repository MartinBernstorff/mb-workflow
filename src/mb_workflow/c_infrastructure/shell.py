import logging
import subprocess
from typing import TYPE_CHECKING

from mb_workflow.d_lib.models import Value

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.directory import ExistingDirectory

logger = logging.getLogger(__name__)


class Command(Value[tuple[str, ...]]):
    @staticmethod
    def fake() -> Command:
        return Command(("gh", "--version"))


class CommandOutput(Value[str]):
    @staticmethod
    def fake() -> CommandOutput:
        return CommandOutput("[]")


class Shell:
    def __init__(self, cwd: ExistingDirectory) -> None:
        self._cwd = cwd

    def cwd(self) -> ExistingDirectory:
        return self._cwd

    def at(self, directory: ExistingDirectory) -> Shell:
        return Shell(directory)

    def run(self, command: Command) -> CommandOutput:
        logger.debug("Running %s", " ".join(command.root))
        result = subprocess.run(
            command.root, cwd=self._cwd.root, capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, command.root, result.stdout, result.stderr
            )
        return CommandOutput(result.stdout)
