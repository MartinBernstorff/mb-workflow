import logging
from typing import TYPE_CHECKING

import pytest

from mb_workflow.b_core.b_domain_services.lock import AlreadyRunningError, LockName, LockPath

if TYPE_CHECKING:
    from pathlib import Path


def test_the_lock_lives_in_the_cache_under_its_name() -> None:
    assert LockPath.of(LockName.fake()).root.name == "review-workspaces.lock"


def test_a_free_lock_lets_the_run_proceed(tmp_path: Path) -> None:
    lock = LockPath(tmp_path / "nested" / "review-workspaces.lock")
    with lock.held():
        assert lock.root.exists()


def test_a_second_run_is_refused_while_the_first_holds_the_lock(tmp_path: Path) -> None:
    lock = LockPath(tmp_path / "review-workspaces.lock")
    with (
        lock.held(),
        pytest.raises(AlreadyRunningError, match="another run holds"),
        LockPath(lock.root).held(),
    ):
        pytest.fail("the second run should not have entered")


def test_the_lock_is_free_again_once_the_run_ends(tmp_path: Path) -> None:
    lock = LockPath(tmp_path / "review-workspaces.lock")
    with lock.held():
        pass
    with lock.held():
        assert lock.root.exists()


def test_the_lock_is_released_when_the_run_raises(tmp_path: Path) -> None:
    lock = LockPath(tmp_path / "review-workspaces.lock")
    with pytest.raises(ValueError, match="boom"), lock.held():
        raise ValueError("boom")
    with lock.held():
        assert lock.root.exists()


def test_logs_taking_and_releasing_the_lock(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    lock = LockPath(tmp_path / "review-workspaces.lock")
    with caplog.at_level(logging.INFO), lock.held():
        assert "Holding" in caplog.text
    assert "Released" in caplog.text
