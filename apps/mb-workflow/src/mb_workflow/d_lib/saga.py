import logging
from typing import TYPE_CHECKING, Protocol

from safe_result import Ok, Result

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


class SagaStep[E: Exception](Protocol):
    def apply(self) -> Result[None, E]: ...

    def revert(self) -> Result[None, Exception]: ...


class Saga:
    @staticmethod
    def run[E: Exception](steps: Sequence[SagaStep[E]]) -> Result[None, E]:
        completed: list[SagaStep[E]] = []
        for step in steps:
            try:
                applied = step.apply()
            except BaseException:
                Saga.revert(completed)
                raise
            if applied.is_err():
                Saga.revert(completed)
                return applied
            completed.append(step)
        return Ok(None)

    @staticmethod
    def revert(completed: Sequence[SagaStep[Exception]]) -> None:
        for step in reversed(completed):
            reverted = step.revert()
            if reverted.is_err():
                logger.warning("Could not revert %s: %s", type(step).__name__, reverted.error)
