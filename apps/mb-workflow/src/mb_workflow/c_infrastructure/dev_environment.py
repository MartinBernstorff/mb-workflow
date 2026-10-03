import logging

from mb_workflow.c_infrastructure.shell import Command, CommandRunner

logger = logging.getLogger(__name__)


class DevEnvironment:
    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner

    def set_up(self) -> None:
        for command in (Command(("uv", "sync")), Command(("uv", "run", "lefthook", "install"))):
            logger.info("Running %s", " ".join(command.root))
            _ = self._runner.run(command)
