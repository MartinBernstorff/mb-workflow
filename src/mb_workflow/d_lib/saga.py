import logging
from typing import TYPE_CHECKING, Protocol

from safe_result import Ok, Result

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


# A step returns its own failure as a value, having undone whatever part of itself it got done.
class SagaStep(Protocol):
    def apply(self) -> Result[None, Exception]: ...

    def revert(self) -> Result[None, Exception]: ...


class Saga:
    # Applies the steps in order; when one fails, reverts the completed ones in reverse order.
    @staticmethod
    def run(steps: Sequence[SagaStep]) -> Result[None, Exception]:
        completed: list[SagaStep] = []
        for step in steps:
            try:
                applied = step.apply()
            # BaseException too: an interruption, such as a second stop signal, must not strand the completed steps.
            except BaseException:
                Saga.revert(completed)
                raise
            if applied.is_err():
                Saga.revert(completed)
                return applied
            completed.append(step)
        return Ok(None)

    # A failed revert is logged rather than returned, so the steps before it are still reverted.
    @staticmethod
    def revert(completed: Sequence[SagaStep]) -> None:
        for step in reversed(completed):
            reverted = step.revert()
            if reverted.is_err():
                logger.warning("Could not revert %s: %s", type(step).__name__, reverted.error)
