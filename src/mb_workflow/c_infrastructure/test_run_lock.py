import logging
from enum import StrEnum
from typing import TYPE_CHECKING

import pytest

from mb_workflow.b_core.c_secondary_ports.run_lock import AlreadyRunningError, FakeRunLock
from mb_workflow.b_core.d_domain_model.workspace import ProjectSelector
from mb_workflow.c_infrastructure.flock import FlockRunLock, LockName, LockPath

if TYPE_CHECKING:
    from pathlib import Path

    from mb_workflow.b_core.c_secondary_ports.run_lock import RunLock


class LockKind(StrEnum):
    fake = "fake"
    flock = "flock"


@pytest.fixture(params=list(LockKind))
def lock(request: pytest.FixtureRequest, tmp_path: Path) -> RunLock:
    if LockKind(request.param) == LockKind.fake:
        return FakeRunLock()
    return FlockRunLock(LockPath(tmp_path / "nested" / "review-workspaces.lock"))


def test_a_free_lock_lets_the_run_proceed(lock: RunLock) -> None:
    entered = False
    with lock.held():
        entered = True
    assert entered


def test_a_second_holder_is_refused_while_the_first_holds_the_lock(lock: RunLock) -> None:
    with (
        lock.held(),
        pytest.raises(AlreadyRunningError, match="another run holds"),
        lock.held(),
    ):
        pytest.fail("the second run should not have entered")


def test_the_lock_is_free_again_once_the_run_ends(lock: RunLock) -> None:
    with lock.held():
        pass
    with lock.held():
        pass


def test_the_lock_is_released_when_the_run_raises(lock: RunLock) -> None:
    with pytest.raises(ValueError, match="boom"), lock.held():
        raise ValueError("boom")
    with lock.held():
        pass


def test_the_lock_lives_in_the_cache_under_its_name() -> None:
    assert LockPath.of(LockName.fake()).root.name == "review-workspaces.lock"


def test_a_project_lock_lives_in_the_cache_under_the_project() -> None:
    path = LockPath.of_project(LockName("drain"), ProjectSelector("github:owner/repo")).root
    assert path.parts[-2:] == ("github-owner-repo", "drain.lock")


def test_projects_get_separate_locks() -> None:
    assert LockPath.of_project(LockName("drain"), ProjectSelector("github:owner/one")) != (
        LockPath.of_project(LockName("drain"), ProjectSelector("github:owner/two"))
    )


def test_a_separate_flock_on_the_same_path_is_refused(tmp_path: Path) -> None:
    path = LockPath(tmp_path / "review-workspaces.lock")
    with (
        FlockRunLock(path).held(),
        pytest.raises(AlreadyRunningError),
        FlockRunLock(path).held(),
    ):
        pytest.fail("the second run should not have entered")


def test_logs_taking_and_releasing_the_flock(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    lock = FlockRunLock(LockPath(tmp_path / "review-workspaces.lock"))
    with caplog.at_level(logging.DEBUG), lock.held():
        assert "Holding" in caplog.text
    assert "Released" in caplog.text
