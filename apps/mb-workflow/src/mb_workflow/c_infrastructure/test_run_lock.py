import logging
from enum import StrEnum
from typing import TYPE_CHECKING

import pytest
from assertions import Assert

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
    with lock.acquire().unwrap():
        entered = True
    Assert.that(entered).is_true()


def test_a_second_holder_is_refused_while_the_first_holds_the_lock(lock: RunLock) -> None:
    refusal = "another run holds"
    with lock.acquire().unwrap():
        second = lock.acquire()
    error = Assert.that(second).is_err(AlreadyRunningError)
    Assert.that(str(error)).contains(refusal)


def test_a_refused_holder_leaves_the_lock_with_the_first(lock: RunLock) -> None:
    with lock.acquire().unwrap():
        _ = lock.acquire()
        third = lock.acquire()
    _ = Assert.that(third).is_err(AlreadyRunningError)


def test_the_lock_is_free_again_once_the_run_ends(lock: RunLock) -> None:
    with lock.acquire().unwrap():
        pass
    with lock.acquire().unwrap():
        pass


def test_the_lock_is_released_when_the_run_raises(lock: RunLock) -> None:
    with pytest.raises(ValueError, match="boom"), lock.acquire().unwrap():
        raise ValueError("boom")
    with lock.acquire().unwrap():
        pass


def test_the_lock_lives_in_the_cache_under_its_name() -> None:
    filename = "review-workspaces.lock"
    Assert.that(LockPath.of(LockName.fake()).root.name).matches(filename)


def test_a_project_lock_lives_in_the_cache_under_the_project() -> None:
    name = LockName.fake()
    project = ProjectSelector("github:owner/repo")
    directory = "github-owner-repo"
    path = LockPath.of_project(name, project).root
    Assert.that(path.parts[-2:]).matches((directory, f"{name.root}.lock"))


def test_projects_get_separate_locks() -> None:
    name = LockName.fake()
    one = LockPath.of_project(name, ProjectSelector("github:owner/one"))
    two = LockPath.of_project(name, ProjectSelector("github:owner/two"))
    Assert.that(one).not_().matches(two)


def test_a_separate_flock_on_the_same_path_is_refused(tmp_path: Path) -> None:
    path = LockPath(tmp_path / "review-workspaces.lock")
    with FlockRunLock(path).acquire().unwrap():
        second = FlockRunLock(path).acquire()
    _ = Assert.that(second).is_err(AlreadyRunningError)


def test_logs_taking_and_releasing_the_flock(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    lock = FlockRunLock(LockPath(tmp_path / "review-workspaces.lock"))
    with caplog.at_level(logging.DEBUG), lock.acquire().unwrap():
        Assert.that(caplog.text).contains("Holding")
    Assert.that(caplog.text).contains("Released")
