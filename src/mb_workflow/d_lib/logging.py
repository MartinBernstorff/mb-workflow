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

    def configure(self) -> None:
        logging.basicConfig(level=self.root, format="%(message)s")
        for name in ("httpx", "httpcore"):
            logging.getLogger(name).setLevel(logging.WARNING)


# A step that may be slow, named as a capitalised gerund phrase, e.g. "Claiming MB-57".
class Activity(Value[str]):
    @staticmethod
    def fake() -> Activity:
        return Activity("Claiming MB-57")

    # Logs the start and the finish with the time taken, so a slow run shows which step stalled.
    @contextmanager
    def logged(self, logger: logging.Logger) -> Generator[None]:
        logger.info("%s…", self.root)
        began = time.monotonic()
        try:
            yield
        except BaseException:
            logger.info("%s failed after %.1fs.", self.root, time.monotonic() - began)
            raise
        logger.info("%s took %.1fs.", self.root, time.monotonic() - began)
