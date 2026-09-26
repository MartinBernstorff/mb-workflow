import logging
from typing import TYPE_CHECKING

import pytest

from mb_workflow.d_lib.logging import LogLevel, configure

if TYPE_CHECKING:
    from collections.abc import Iterator

HTTP_LOGGERS = ("httpx", "httpcore")


@pytest.fixture(autouse=True)
def _restore_http_levels(caplog: pytest.LogCaptureFixture) -> Iterator[None]:
    caplog.set_level(logging.INFO)
    levels = {name: logging.getLogger(name).level for name in HTTP_LOGGERS}
    yield
    for name, level in levels.items():
        logging.getLogger(name).setLevel(level)


@pytest.mark.parametrize("name", HTTP_LOGGERS)
def test_http_loggers_hide_info_but_show_warnings(name: str) -> None:
    configure(LogLevel(logging.INFO))

    logger = logging.getLogger(name)
    assert not logger.isEnabledFor(logging.INFO)
    assert logger.isEnabledFor(logging.WARNING)
