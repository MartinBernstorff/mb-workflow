import logging
import subprocess
from pathlib import Path

from pydantic import model_validator

from mb_workflow.d_lib.models import Value

logger = logging.getLogger(__name__)


class ExistingDirectory(Value[Path]):
    @model_validator(mode="after")
    def directory_exists(self) -> ExistingDirectory:
        if not self.root.is_dir():
            raise ValueError(f"Not a directory: {self.root}")
        return self

    @staticmethod
    def fake() -> ExistingDirectory:
        return ExistingDirectory(Path.cwd())


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
