import logging
import re
from typing import TYPE_CHECKING

import pytest

from mb_workflow.d_lib.logging import Activity, LogLevel, configure

if TYPE_CHECKING:
    from collections.abc import Iterator

HTTP_LOGGERS = ("httpx", "httpcore")


@pytest.fixture(autouse=True)
def _root_at_info_and_http_levels_restored(caplog: pytest.LogCaptureFixture) -> Iterator[None]:
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


def test_an_activity_logs_its_start_before_the_work_and_its_finish_after(
    caplog: pytest.LogCaptureFixture,
) -> None:
    activity = Activity.fake()
    work = "working"
    logger = logging.getLogger(__name__)
    with activity.logged(logger):
        logger.info(work)

    started, worked, finished = caplog.messages
    assert started == f"Started {activity.root}."
    assert worked == work
    assert re.fullmatch(rf"Finished {activity.root} in \d+\.\ds\.", finished)


def test_an_activity_that_raises_logs_its_failure_and_reraises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    activity = Activity.fake()
    with pytest.raises(LookupError), activity.logged(logging.getLogger(__name__)):
        raise LookupError

    _, failed = caplog.messages
    assert re.fullmatch(rf"Failed {activity.root} after \d+\.\ds\.", failed)
