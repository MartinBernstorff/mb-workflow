import logging
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING

from pydantic import RootModel

from mb_workflow.d_lib.models import Value

if TYPE_CHECKING:
    from collections.abc import Generator


class LogLevel(RootModel[int]):
    @staticmethod
    def fake() -> LogLevel:
        return LogLevel(logging.INFO)


def configure(level: LogLevel) -> None:
    logging.basicConfig(level=level.root, format="%(message)s")
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


# A step that may be slow, named so it reads after "Started", e.g. "claiming MB-57".
class Activity(Value[str]):
    @staticmethod
    def fake() -> Activity:
        return Activity("claiming MB-57")

    # Logs the start and the finish with the time taken, so a slow run shows which step stalled.
    @contextmanager
    def logged(self, logger: logging.Logger) -> Generator[None]:
        logger.info("Started %s.", self.root)
        began = time.monotonic()
        try:
            yield
        except BaseException:
            logger.info("Failed %s after %.1fs.", self.root, time.monotonic() - began)
            raise
        logger.info("Finished %s in %.1fs.", self.root, time.monotonic() - began)
