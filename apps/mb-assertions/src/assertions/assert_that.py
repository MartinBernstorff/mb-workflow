import re
from collections.abc import Callable, Iterable, Sequence, Sized
from typing import Protocol, overload, override

import pydantic

from assertions.populated_differences import (
    FieldDifference,
    ListComparison,
    PopulatedDifferences,
)


class _HoldsActual[T](Protocol):
    @property
    def actual(self) -> T: ...


class _NegatableMatchers[T](Protocol):
    """The matchers both That and Not implement, so negation stays in sync."""

    @property
    def actual(self) -> T: ...

    def matches(self, expected: T) -> None: ...

    def contains(self: _HoldsActual[str], substring: str) -> None: ...

    def matches_pattern(self: _HoldsActual[str], pattern: str) -> None: ...

    def starts_with(self: _HoldsActual[str], prefix: str) -> None: ...

    def ends_with(self: _HoldsActual[str], suffix: str) -> None: ...


class _Values:
    @staticmethod
    def equal[T](actual: T, expected: T) -> bool:
        if isinstance(actual, pydantic.BaseModel) and isinstance(expected, pydantic.BaseModel):
            return actual.model_dump() == expected.model_dump()
        return actual == expected


class That[T](_NegatableMatchers[T]):
    def __init__(self, actual: T) -> None:
        self._actual = actual

    @property
    @override
    def actual(self) -> T:
        return self._actual

    @override
    def matches(self, expected: T) -> None:
        if not _Values.equal(self._actual, expected):
            raise AssertionError(self._mismatch(self._actual, expected))

    def matches_populated_exactly(self, expected: T) -> None:
        That._raise_on_differences(
            PopulatedDifferences.between(self._actual, expected, ListComparison.EXACTLY),
        )

    def matches_populated_containing(self, expected: T) -> None:
        That._raise_on_differences(
            PopulatedDifferences.between(self._actual, expected, ListComparison.CONTAINING),
        )

    def in_container(self, container: Iterable[T]) -> None:
        if self._actual not in container:
            raise AssertionError(f"Item {self._actual} not found in container {container}")

    def not_in_container(self, container: Iterable[T]) -> None:
        if self._actual in container:
            raise AssertionError(
                f"Item {self._actual} unexpectedly found in container {container}",
            )

    def has_length(self: _HoldsActual[Sized], length: int) -> None:
        if len(self.actual) != length:
            raise AssertionError(
                f"Expected length {length}, but it had length {len(self.actual)}: {self.actual}",
            )

    @override
    def contains(self: _HoldsActual[str], substring: str) -> None:
        if substring not in self.actual:
            raise AssertionError(f"Expected {self.actual!r} to contain {substring!r}")

    @override
    def matches_pattern(self: _HoldsActual[str], pattern: str) -> None:
        if re.search(pattern, self.actual) is None:
            raise AssertionError(f"Expected {self.actual!r} to match pattern {pattern!r}")

    @override
    def starts_with(self: _HoldsActual[str], prefix: str) -> None:
        if not self.actual.startswith(prefix):
            raise AssertionError(f"Expected {self.actual!r} to start with {prefix!r}")

    @override
    def ends_with(self: _HoldsActual[str], suffix: str) -> None:
        if not self.actual.endswith(suffix):
            raise AssertionError(f"Expected {self.actual!r} to end with {suffix!r}")

    def is_true(self: _HoldsActual[bool]) -> None:
        if self.actual is not True:
            raise AssertionError(f"Expected True, but it was {self.actual}")

    def is_false(self: _HoldsActual[bool]) -> None:
        if self.actual is not False:
            raise AssertionError(f"Expected False, but it was {self.actual}")

    def is_instance[S](self, cls: type[S]) -> S:
        if isinstance(self._actual, cls):
            return self._actual
        raise AssertionError(
            f"Expected an instance of {cls.__name__}, but got "
            f"{type(self._actual).__name__}: {self._actual}",
        )

    def exists[S](self: _HoldsActual[S | None]) -> S:
        if self.actual is None:
            raise AssertionError("Expected value to exist, but it was None")
        return self.actual

    def not_(self) -> "Not[T]":
        return Not(self._actual)

    @staticmethod
    def _mismatch(actual: T, expected: T) -> str:
        if isinstance(actual, pydantic.BaseModel) and isinstance(expected, pydantic.BaseModel):
            return (
                "Expected entity model values to match, but they did not: "
                f"{actual.model_dump()} != {expected.model_dump()}"
            )
        return f"Expected values to match, but they did not: {actual} != {expected}"

    @staticmethod
    def _raise_on_differences(differences: list[FieldDifference]) -> None:
        if not differences:
            return
        raise AssertionError(
            "Expected the populated fields to match, but they did not:\n"
            + "\n".join(f"\t{difference.rendered()}" for difference in differences),
        )


class Not[T](_NegatableMatchers[T]):
    def __init__(self, actual: T) -> None:
        self._actual = actual

    @property
    @override
    def actual(self) -> T:
        return self._actual

    @override
    def matches(self, expected: T) -> None:
        if _Values.equal(self._actual, expected):
            raise AssertionError(f"Expected values to differ, but both were {self._actual}")

    @override
    def contains(self: _HoldsActual[str], substring: str) -> None:
        if substring in self.actual:
            raise AssertionError(f"Expected {self.actual!r} not to contain {substring!r}")

    @override
    def matches_pattern(self: _HoldsActual[str], pattern: str) -> None:
        if re.search(pattern, self.actual) is not None:
            raise AssertionError(f"Expected {self.actual!r} not to match pattern {pattern!r}")

    @override
    def starts_with(self: _HoldsActual[str], prefix: str) -> None:
        if self.actual.startswith(prefix):
            raise AssertionError(f"Expected {self.actual!r} not to start with {prefix!r}")

    @override
    def ends_with(self: _HoldsActual[str], suffix: str) -> None:
        if self.actual.endswith(suffix):
            raise AssertionError(f"Expected {self.actual!r} not to end with {suffix!r}")


class ThatElements[T, E](That[T]):
    def __init__(self, actual: T, elements: Iterable[E]) -> None:
        super().__init__(actual)
        self._elements = list(elements)

    @override
    def matches(self, expected: T) -> None:
        if isinstance(self._actual, Sequence) and isinstance(expected, Sequence):
            if list(self._actual) != list(expected):
                raise AssertionError(self._mismatch(self._actual, expected))
            return
        super().matches(expected)

    def container_exactly(self, expected: Iterable[E]) -> None:
        expected_items = list(expected)
        missing_items = [item for item in expected_items if item not in self._elements]
        extra_items = [item for item in self._elements if item not in expected_items]
        if missing_items or extra_items:
            raise AssertionError(
                "Expected container to contain exactly the items, but it did not.\n"
                f"\tMissing: {missing_items}\n"
                f"\tExtra: {extra_items}",
            )

    def all_in(self, container: Iterable[E]) -> None:
        container_items = list(container)
        missing_items = [item for item in self._elements if item not in container_items]
        if missing_items:
            raise AssertionError(f"Items not found in container: {missing_items}")

    def none_in(self, container: Iterable[E]) -> None:
        container_items = list(container)
        present_items = [item for item in self._elements if item in container_items]
        if present_items:
            raise AssertionError(f"Unexpected items found in container: {present_items}")

    def all(self, predicate: Callable[[E], bool], message: Callable[[E], str]) -> None:
        failures = [message(item) for item in self._elements if not predicate(item)]
        if failures:
            raise AssertionError(
                f"Expected all items to satisfy predicate, but some did not: {failures}",
            )


class Assert:
    @overload
    @staticmethod
    def that(actual: str) -> That[str]: ...

    @overload
    @staticmethod
    def that[E](actual: Sequence[E]) -> ThatElements[Sequence[E], E]: ...

    @overload
    @staticmethod
    def that[E](actual: set[E]) -> ThatElements[set[E], E]: ...

    @overload
    @staticmethod
    def that[E](actual: frozenset[E]) -> ThatElements[frozenset[E], E]: ...

    @overload
    @staticmethod
    def that[T](actual: T) -> That[T]: ...

    @staticmethod
    def that(actual: object) -> object:
        match actual:
            case str():
                return That(actual)
            case Sequence() | set() | frozenset():
                return ThatElements(actual, actual)
            case _:
                return That(actual)
