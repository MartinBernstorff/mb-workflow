import subprocess
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True, scope="session")
def _git_ignores_the_calling_repository() -> Iterator[None]:
    # Git hooks export GIT_DIR and friends, which would point a test's git subprocesses at the real repo.
    local = subprocess.run(
        ("git", "rev-parse", "--local-env-vars"), capture_output=True, text=True, check=True
    ).stdout.split()
    with pytest.MonkeyPatch.context() as patch:
        for name in local:
            patch.delenv(name, raising=False)
        yield
