from subprocess import CalledProcessError
from typing import override

import pytest

from mb_workflow.c_infrastructure.dev_environment import DevEnvironment
from mb_workflow.c_infrastructure.shell import (
    Command,
    CommandOutput,
    CommandRunner,
    ExistingDirectory,
)


class RecordingRunner(CommandRunner):
    def __init__(self, failing: Command | None = None) -> None:
        self._failing = failing
        self.ran: list[Command] = []

    @override
    def cwd(self) -> ExistingDirectory:
        return ExistingDirectory.fake()

    @override
    def at(self, directory: ExistingDirectory) -> RecordingRunner:
        return self

    @override
    def run(self, command: Command) -> CommandOutput:
        self.ran.append(command)
        if command == self._failing:
            raise CalledProcessError(1, command.root)
        return CommandOutput("")


def test_syncs_dependencies_before_installing_the_git_hooks() -> None:
    runner = RecordingRunner()

    DevEnvironment(runner).set_up()

    assert runner.ran == [Command(("uv", "sync")), Command(("uv", "run", "lefthook", "install"))]


def test_a_failed_sync_stops_before_the_git_hooks_are_installed() -> None:
    runner = RecordingRunner(failing=Command(("uv", "sync")))

    with pytest.raises(CalledProcessError):
        DevEnvironment(runner).set_up()

    assert runner.ran == [Command(("uv", "sync"))]
