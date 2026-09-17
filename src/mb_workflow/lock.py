import fcntl
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from mb_workflow.models import Value

if TYPE_CHECKING:
    from collections.abc import Generator

logger = logging.getLogger(__name__)


class AlreadyRunningError(Exception):
    pass


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
        return LockPath(Path.home() / ".cache" / "mb-workflow" / f"{name.root}.lock")

    @contextmanager
    def held(self) -> Generator[None]:
        self.root.parent.mkdir(parents=True, exist_ok=True)
        with self.root.open("w") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise AlreadyRunningError(
                    f"another run holds {self.root}; it is still creating workspaces"
                ) from error
            logger.info("Holding %s", self.root)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
                logger.info("Released %s", self.root)
