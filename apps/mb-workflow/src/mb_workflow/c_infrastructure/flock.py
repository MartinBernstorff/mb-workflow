import fcntl
import logging
import re
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, TextIO, override

from safe_result import Err, Ok, Result, safe_with

from mb_workflow.b_core.c_secondary_ports.run_lock import AlreadyRunningError, RunLock
from mb_workflow.b_core.d_domain_model.cache import CacheDirectory
from mb_workflow.d_lib.models import Value

if TYPE_CHECKING:
    from collections.abc import Generator

    from mb_workflow.b_core.d_domain_model.workspace import ProjectSelector

logger = logging.getLogger(__name__)


class LockName(Value[str]):
    @staticmethod
    def fake() -> LockName:
        return LockName("review-workspaces")


class LockPath(Value[Path]):
    @staticmethod
    def fake() -> LockPath:
        return LockPath.of(LockName.fake())

    @staticmethod
    def of(name: LockName) -> LockPath:
        return LockPath(CacheDirectory.of_user().root / f"{name.root}.lock")

    # The selector holds characters like ":" and "/", so it is reduced to a single directory name.
    @staticmethod
    def of_project(name: LockName, project: ProjectSelector) -> LockPath:
        directory = re.sub(r"[^A-Za-z0-9]+", "-", project.root).strip("-")
        return LockPath(CacheDirectory.of_user().root / directory / f"{name.root}.lock")


class FlockRunLock(RunLock):
    def __init__(self, path: LockPath) -> None:
        self._path = path

    @override
    @contextmanager
    def held(self) -> Generator[Result[None, AlreadyRunningError]]:
        path = self._path.root
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as handle:
            if FlockRunLock.taken(handle).is_err():
                yield Err(AlreadyRunningError(f"another run holds {path}"))
                return
            logger.debug("Holding %s", path)
            try:
                yield Ok(None)
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
                logger.debug("Released %s", path)

    @staticmethod
    @safe_with(BlockingIOError)
    def taken(handle: TextIO) -> None:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
