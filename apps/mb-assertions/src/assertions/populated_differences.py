import enum
from typing import assert_never

import pydantic


class ListComparison(enum.StrEnum):
    EXACTLY = "exactly"
    CONTAINING = "containing"


class FieldPath(pydantic.RootModel[str]):
    def child(self, field: "FieldName") -> "FieldPath":
        return FieldPath(field.root if not self.root else f"{self.root}.{field.root}")

    def element(self, index: "ElementIndex") -> "FieldPath":
        return FieldPath(f"{self.root}[{index.root}]")


class FieldName(pydantic.RootModel[str]): ...


class ElementIndex(pydantic.RootModel[int]): ...


class RenderedValue(pydantic.RootModel[str]):
    @staticmethod
    def of[T](value: T) -> "RenderedValue":
        if isinstance(value, pydantic.RootModel):
            root: object = value.root
            return RenderedValue(str(root))
        if isinstance(value, pydantic.BaseModel):
            return RenderedValue(value.model_dump_json())
        return RenderedValue(str(value))

    @staticmethod
    def type_of[T](value: T) -> "RenderedValue":
        if isinstance(value, pydantic.BaseModel) and not isinstance(value, pydantic.RootModel):
            return RenderedValue(type(value).__name__)
        return RenderedValue.of(value)

    @staticmethod
    def count_of[T](values: list[T]) -> "RenderedValue":
        return RenderedValue(f"{len(values)} element{'' if len(values) == 1 else 's'}")


class FieldDifference(pydantic.BaseModel):
    path: FieldPath
    actual: RenderedValue
    expected: RenderedValue

    def rendered(self) -> str:
        if self.path.root:
            return f"{self.path.root}: {self.actual.root} != {self.expected.root}"
        return f"{self.actual.root} != {self.expected.root}"


class PopulatedDifferences:
    """Compares only the fields populated on the expected value, recursing into models and lists."""

    @staticmethod
    def between[T](actual: T, expected: T, comparison: ListComparison) -> list[FieldDifference]:
        return PopulatedDifferences._at(actual, expected, FieldPath(""), comparison)

    @staticmethod
    def _at[T](
        actual: T,
        expected: T,
        path: FieldPath,
        comparison: ListComparison,
    ) -> list[FieldDifference]:
        if type(actual) is not type(expected):
            return [
                FieldDifference(
                    path=path,
                    actual=RenderedValue.type_of(actual),
                    expected=RenderedValue.type_of(expected),
                ),
            ]
        if (
            isinstance(expected, pydantic.BaseModel)
            and isinstance(actual, pydantic.BaseModel)
            and not isinstance(expected, pydantic.RootModel)
        ):
            return [
                difference
                for field in expected.model_fields_set
                for difference in PopulatedDifferences._at(
                    getattr(actual, field),
                    getattr(expected, field),
                    path.child(FieldName(field)),
                    comparison,
                )
            ]
        if isinstance(expected, list) and isinstance(actual, list):
            return PopulatedDifferences._in_lists(actual, expected, path, comparison)
        if actual == expected:
            return []
        return [
            FieldDifference(
                path=path,
                actual=RenderedValue.of(actual),
                expected=RenderedValue.of(expected),
            ),
        ]

    @staticmethod
    def _in_lists[T](
        actual: list[T],
        expected: list[T],
        path: FieldPath,
        comparison: ListComparison,
    ) -> list[FieldDifference]:
        match comparison:
            case ListComparison.EXACTLY:
                return PopulatedDifferences._in_exact_lists(actual, expected, path, comparison)
            case ListComparison.CONTAINING:
                return PopulatedDifferences._in_containing_lists(actual, expected, path, comparison)
            case _:
                assert_never(comparison)

    @staticmethod
    def _in_exact_lists[T](
        actual: list[T],
        expected: list[T],
        path: FieldPath,
        comparison: ListComparison,
    ) -> list[FieldDifference]:
        if len(actual) != len(expected):
            return [
                FieldDifference(
                    path=path,
                    actual=RenderedValue.count_of(actual),
                    expected=RenderedValue.count_of(expected),
                ),
            ]
        return [
            difference
            for index, (actual_element, expected_element) in enumerate(
                zip(actual, expected, strict=True),
            )
            for difference in PopulatedDifferences._at(
                actual_element,
                expected_element,
                path.element(ElementIndex(index)),
                comparison,
            )
        ]

    @staticmethod
    def _in_containing_lists[T](
        actual: list[T],
        expected: list[T],
        path: FieldPath,
        comparison: ListComparison,
    ) -> list[FieldDifference]:
        return [
            FieldDifference(
                path=path,
                actual=RenderedValue("<missing>"),
                expected=RenderedValue.of(expected_element),
            )
            for expected_element in expected
            if not any(
                not PopulatedDifferences._at(actual_element, expected_element, path, comparison)
                for actual_element in actual
            )
        ]
