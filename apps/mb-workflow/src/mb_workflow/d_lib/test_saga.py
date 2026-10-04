from typing import override

import pytest
from assertions import Assert
from safe_result import Err, Ok, Result

from mb_workflow.d_lib.models import Value
from mb_workflow.d_lib.saga import Saga, SagaStep


class StepName(Value[str]):
    pass


class Event(Value[str]):
    pass


class Journal:
    def __init__(self) -> None:
        self._events: list[Event] = []

    def record(self, event: Event) -> None:
        self._events.append(event)

    def events(self) -> tuple[Event, ...]:
        return tuple(self._events)


class StepError(Exception):
    pass


class RecordingStep(SagaStep[StepError]):
    def __init__(self, name: StepName, journal: Journal) -> None:
        self._name = name
        self._journal = journal

    @override
    def apply(self) -> Result[None, StepError]:
        self._journal.record(Event(f"apply {self._name.root}"))
        return Ok(None)

    @override
    def revert(self) -> Result[None, Exception]:
        self._journal.record(Event(f"revert {self._name.root}"))
        return Ok(None)


class FailingStep(RecordingStep):
    def __init__(self, name: StepName, journal: Journal, error: StepError) -> None:
        super().__init__(name, journal)
        self._error = error

    @override
    def apply(self) -> Result[None, StepError]:
        _ = super().apply()
        return Err(self._error)


class UnrevertableStep(RecordingStep):
    @override
    def revert(self) -> Result[None, Exception]:
        _ = super().revert()
        return Err(StepError("revert failed"))


class InterruptedStep(RecordingStep):
    @override
    def apply(self) -> Result[None, StepError]:
        _ = super().apply()
        raise KeyboardInterrupt


def test_a_saga_that_succeeds_reverts_no_step() -> None:
    journal = Journal()
    first, second = StepName("first"), StepName("second")
    result = Saga.run((RecordingStep(first, journal), RecordingStep(second, journal)))
    Assert.that(result).matches(Ok(None))
    Assert.that(journal.events()).matches(
        (Event(f"apply {first.root}"), Event(f"apply {second.root}"))
    )


def test_a_failed_step_reverts_the_completed_steps_in_reverse_order() -> None:
    journal = Journal()
    first, second, third = StepName("first"), StepName("second"), StepName("third")
    _ = Saga.run(
        (
            RecordingStep(first, journal),
            RecordingStep(second, journal),
            FailingStep(third, journal, StepError()),
            RecordingStep(StepName("never"), journal),
        )
    )
    Assert.that(journal.events()).matches(
        (
            Event(f"apply {first.root}"),
            Event(f"apply {second.root}"),
            Event(f"apply {third.root}"),
            Event(f"revert {second.root}"),
            Event(f"revert {first.root}"),
        )
    )


def test_a_failed_saga_returns_the_error_of_the_failed_step() -> None:
    failure = StepError("the step failed")
    result = Saga.run((FailingStep(StepName("only"), Journal(), failure),))
    Assert.that(result).matches(Err(failure))


def test_a_failed_revert_still_reverts_the_steps_before_it() -> None:
    journal = Journal()
    first, second = StepName("first"), StepName("second")
    _ = Saga.run(
        (
            RecordingStep(first, journal),
            UnrevertableStep(second, journal),
            FailingStep(StepName("third"), journal, StepError()),
        )
    )
    Assert.that(journal.events()[-2:]).matches(
        (Event(f"revert {second.root}"), Event(f"revert {first.root}"))
    )


def test_an_interrupted_step_reverts_the_completed_steps_and_reraises() -> None:
    journal = Journal()
    first = StepName("first")
    with pytest.raises(KeyboardInterrupt):
        _ = Saga.run((RecordingStep(first, journal), InterruptedStep(StepName("second"), journal)))
    Assert.that(journal.events()[-1]).matches(Event(f"revert {first.root}"))
