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
    from contextlib import AbstractContextManager

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

    @staticmethod
    def of_project(name: LockName, project: ProjectSelector) -> LockPath:
        directory = re.sub(r"[^A-Za-z0-9]+", "-", project.root).strip("-")
        return LockPath(CacheDirectory.of_user().root / directory / f"{name.root}.lock")


class FlockRunLock(RunLock):
    def __init__(self, path: LockPath) -> None:
        self._path = path

    @override
    def acquire(self) -> Result[AbstractContextManager[None], AlreadyRunningError]:
        path = self._path.root
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("w")
        if FlockRunLock.acquire_exclusive(handle).is_err():
            handle.close()
            return Err(AlreadyRunningError(f"another run holds {path}"))
        logger.debug("Holding %s", path)
        return Ok(FlockRunLock.released_on_exit(handle, self._path))

    @staticmethod
    @safe_with(BlockingIOError)
    def acquire_exclusive(handle: TextIO) -> None:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    @contextmanager
    def released_on_exit(handle: TextIO, path: LockPath) -> Generator[None]:
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
            handle.close()
            logger.debug("Released %s", path.root)
