import logging

from pydantic import RootModel


class LogLevel(RootModel[int]):
    @staticmethod
    def fake() -> LogLevel:
        return LogLevel(logging.INFO)


def configure(level: LogLevel) -> None:
    logging.basicConfig(level=level.root, format="%(message)s")
