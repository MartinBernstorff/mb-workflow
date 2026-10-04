import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pydantic
import pytest
from safe_result import Err, Ok, Result

from assertions import Assert


class Pet(pydantic.BaseModel):
    name: str
    tags: list[str]


class Owner(pydantic.BaseModel):
    pet: Pet


class Tag(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True)

    name: str


class Tags(pydantic.RootModel[frozenset[Tag]]):
    pass


class Recorded(pydantic.RootModel[bool]):
    pass


class Ready(pydantic.RootModel[bool]):
    pass


class Cleared(pydantic.BaseModel):
    pass


class Pending(pydantic.BaseModel):
    pass


def test_matches_passes_on_equal_values() -> None:
    value = 1

    Assert.that(value).matches(value)


def test_matches_reports_both_values() -> None:
    actual = 1
    expected = 2

    with pytest.raises(AssertionError, match=re.escape(f"{actual} != {expected}")):
        Assert.that(actual).matches(expected)


def test_matches_compares_sequences_by_their_elements() -> None:
    elements = [1, 2]

    Assert.that(elements).matches(tuple(elements))


def test_matches_reports_differing_sequences() -> None:
    actual = [1, 2]
    expected = (2, 1)

    with pytest.raises(AssertionError, match=re.escape(f"{actual} != {expected}")):
        Assert.that(actual).matches(expected)


def test_matches_compares_models_by_value() -> None:
    name = "a"

    Assert.that(Pet(name=name, tags=[])).matches(Pet(name=name, tags=[]))


def test_matches_compares_models_holding_a_frozenset_of_models() -> None:
    tags = frozenset({Tag(name="a"), Tag(name="b")})

    Assert.that(Tags(tags)).matches(Tags(frozenset(tags)))


def test_matches_rejects_root_models_of_different_classes() -> None:
    actual: pydantic.RootModel[bool] = Recorded(True)

    with pytest.raises(AssertionError):
        Assert.that(actual).matches(Ready(True))


def test_matches_rejects_field_less_models_of_different_classes() -> None:
    actual: pydantic.BaseModel = Cleared()

    with pytest.raises(AssertionError):
        Assert.that(actual).matches(Pending())


def test_matches_reports_both_model_reprs() -> None:
    actual: pydantic.RootModel[bool] = Ready(True)
    expected = Recorded(True)

    with pytest.raises(AssertionError, match=re.escape(f"{actual!r} != {expected!r}")):
        Assert.that(actual).matches(expected)


def test_matches_populated_exactly_ignores_unset_fields() -> None:
    name = "a"

    Assert.that(Pet(name=name, tags=["x"])).matches_populated_exactly(
        Pet.model_construct(name=name),
    )


def test_matches_populated_exactly_reports_the_differing_path() -> None:
    with pytest.raises(AssertionError, match=re.escape("tags: 1 element != 2 elements")):
        Assert.that(Pet(name="a", tags=["x"])).matches_populated_exactly(
            Pet.model_construct(tags=["x", "y"]),
        )


def test_matches_populated_exactly_reports_the_nested_element_path() -> None:
    actual_tag = "x"
    expected_tag = "y"

    with pytest.raises(
        AssertionError,
        match=re.escape(f"pet.tags[0]: {actual_tag} != {expected_tag}"),
    ):
        Assert.that(Owner(pet=Pet(name="a", tags=[actual_tag]))).matches_populated_exactly(
            Owner.model_construct(pet=Pet.model_construct(tags=[expected_tag])),
        )


def test_matches_populated_exactly_reports_differing_types_by_name() -> None:
    actual: pydantic.BaseModel = Pet(name="a", tags=[])

    with pytest.raises(AssertionError, match=f"{Pet.__name__} != {Owner.__name__}"):
        Assert.that(actual).matches_populated_exactly(Owner.model_construct())


def test_matches_populated_containing_allows_extra_list_elements() -> None:
    tag = "y"

    Assert.that(Pet(name="a", tags=["x", tag])).matches_populated_containing(
        Pet.model_construct(tags=[tag]),
    )


def test_matches_populated_containing_reports_the_missing_element() -> None:
    missing_tag = "z"

    with pytest.raises(AssertionError, match=f"tags: <missing> != {missing_tag}"):
        Assert.that(Pet(name="a", tags=["x"])).matches_populated_containing(
            Pet.model_construct(tags=[missing_tag]),
        )


def test_in_container_passes_when_present() -> None:
    item = 1

    Assert.that(item).in_container([item, 2])


def test_in_container_reports_item_and_container() -> None:
    item = 3
    container = [1, 2]

    with pytest.raises(
        AssertionError,
        match=re.escape(f"{item} not found in container {container}"),
    ):
        Assert.that(item).in_container(container)


def test_not_in_container_passes_when_absent() -> None:
    Assert.that(3).not_in_container([1, 2])


def test_not_in_container_reports_item_and_container() -> None:
    item = 1
    container = [item, 2]

    with pytest.raises(
        AssertionError,
        match=re.escape(f"{item} unexpectedly found in container {container}"),
    ):
        Assert.that(item).not_in_container(container)


def test_container_exactly_ignores_order() -> None:
    Assert.that([1, 2]).container_exactly({2, 1})


def test_container_exactly_reports_missing_and_extra_items() -> None:
    shared = 2
    missing = 3
    extra = 1

    with pytest.raises(
        AssertionError,
        match=re.escape(f"Missing: {[missing]}\n\tExtra: {[extra]}"),
    ):
        Assert.that([extra, shared]).container_exactly([shared, missing])


def test_all_in_passes_on_a_subset() -> None:
    Assert.that((1, 2)).all_in([1, 2, 3])


def test_all_in_accepts_any_sequence() -> None:
    Assert.that(range(1, 3)).all_in([1, 2, 3])


def test_all_in_reports_the_missing_items() -> None:
    missing = 4

    with pytest.raises(
        AssertionError,
        match=re.escape(f"Items not found in container: {[missing]}"),
    ):
        Assert.that([1, missing]).all_in([1, 2, 3])


def test_none_in_passes_on_disjoint_items() -> None:
    Assert.that(frozenset({4})).none_in([1, 2, 3])


def test_none_in_reports_the_present_items() -> None:
    present = 1

    with pytest.raises(
        AssertionError,
        match=re.escape(f"Unexpected items found in container: {[present]}"),
    ):
        Assert.that([present, 4]).none_in([present, 2, 3])


def test_all_passes_when_every_item_satisfies_the_predicate() -> None:
    Assert.that([2, 4]).all(lambda n: n % 2 == 0, lambda n: f"{n} is odd")


def test_all_reports_each_failing_item() -> None:
    first_odd = 1
    second_odd = 3

    with pytest.raises(
        AssertionError,
        match=re.escape(str([f"{first_odd} is odd", f"{second_odd} is odd"])),
    ):
        Assert.that([first_odd, 2, second_odd]).all(
            lambda n: n % 2 == 0,
            lambda n: f"{n} is odd",
        )


def test_has_length_passes_on_the_length() -> None:
    value = "abc"

    Assert.that(value).has_length(len(value))


def test_has_length_reports_the_length() -> None:
    value = [1]
    expected_length = 2

    with pytest.raises(
        AssertionError,
        match=re.escape(f"length {expected_length}, but it had length {len(value)}: {value}"),
    ):
        Assert.that(value).has_length(expected_length)


def test_is_true_passes_on_true() -> None:
    Assert.that(True).is_true()


def test_is_true_rejects_false() -> None:
    value = False

    with pytest.raises(AssertionError, match=f"Expected True, but it was {value}"):
        Assert.that(value).is_true()


def test_is_false_passes_on_false() -> None:
    Assert.that(False).is_false()


def test_is_false_rejects_true() -> None:
    value = True

    with pytest.raises(AssertionError, match=f"Expected False, but it was {value}"):
        Assert.that(value).is_false()


def test_is_instance_returns_the_narrowed_value() -> None:
    text = "a"
    value: int | str = text

    narrowed: str = Assert.that(value).is_instance(str)

    Assert.that(narrowed).matches(text)


def test_is_instance_reports_the_expected_and_actual_types() -> None:
    value: int | str = 1

    with pytest.raises(
        AssertionError,
        match=f"Expected an instance of {str.__name__}, but got {int.__name__}: {value}",
    ):
        _ = Assert.that(value).is_instance(str)


def test_exists_returns_the_narrowed_value() -> None:
    number = 1
    value: int | None = number

    narrowed: int = Assert.that(value).exists()

    Assert.that(narrowed).matches(number)


def test_exists_rejects_none() -> None:
    value: int | None = None

    with pytest.raises(AssertionError, match="Expected value to exist, but it was None"):
        _ = Assert.that(value).exists()


def test_contains_passes_on_a_substring() -> None:
    substring = "b"

    Assert.that(f"a{substring}c").contains(substring)


def test_contains_reports_the_string_and_the_substring() -> None:
    value = "abc"
    substring = "d"

    with pytest.raises(
        AssertionError,
        match=re.escape(f"Expected {value!r} to contain {substring!r}"),
    ):
        Assert.that(value).contains(substring)


def test_matches_pattern_passes_on_a_partial_match() -> None:
    Assert.that("order 42 shipped").matches_pattern(r"\d+")


def test_matches_pattern_reports_the_string_and_the_pattern() -> None:
    value = "abc"
    pattern = r"\d+"

    with pytest.raises(
        AssertionError,
        match=re.escape(f"Expected {value!r} to match pattern {pattern!r}"),
    ):
        Assert.that(value).matches_pattern(pattern)


def test_starts_with_passes_on_a_prefix() -> None:
    prefix = "a"

    Assert.that(f"{prefix}bc").starts_with(prefix)


def test_starts_with_reports_the_string_and_the_prefix() -> None:
    value = "abc"
    prefix = "b"

    with pytest.raises(
        AssertionError,
        match=re.escape(f"Expected {value!r} to start with {prefix!r}"),
    ):
        Assert.that(value).starts_with(prefix)


def test_starts_with_reads_the_prefix_literally() -> None:
    with pytest.raises(AssertionError):
        Assert.that("abc").starts_with(".")


def test_ends_with_passes_on_a_suffix() -> None:
    suffix = "c"

    Assert.that(f"ab{suffix}").ends_with(suffix)


def test_ends_with_reports_the_string_and_the_suffix() -> None:
    value = "abc"
    suffix = "b"

    with pytest.raises(
        AssertionError,
        match=re.escape(f"Expected {value!r} to end with {suffix!r}"),
    ):
        Assert.that(value).ends_with(suffix)


def test_not_matches_passes_on_different_values() -> None:
    Assert.that(1).not_().matches(2)


def test_not_matches_reports_the_shared_value() -> None:
    value = 1

    with pytest.raises(
        AssertionError,
        match=re.escape(f"Expected values to differ, but both were {value}"),
    ):
        Assert.that(value).not_().matches(value)


def test_not_matches_compares_models_by_value() -> None:
    name = "a"

    with pytest.raises(AssertionError):
        Assert.that(Pet(name=name, tags=[])).not_().matches(Pet(name=name, tags=[]))


def test_not_contains_passes_without_the_substring() -> None:
    Assert.that("abc").not_().contains("d")


def test_not_contains_reports_the_string_and_the_substring() -> None:
    value = "abc"
    substring = "b"

    with pytest.raises(
        AssertionError,
        match=re.escape(f"Expected {value!r} not to contain {substring!r}"),
    ):
        Assert.that(value).not_().contains(substring)


def test_not_matches_pattern_passes_without_a_match() -> None:
    Assert.that("abc").not_().matches_pattern(r"\d+")


def test_not_matches_pattern_reports_the_string_and_the_pattern() -> None:
    value = "order 42"
    pattern = r"\d+"

    with pytest.raises(
        AssertionError,
        match=re.escape(f"Expected {value!r} not to match pattern {pattern!r}"),
    ):
        Assert.that(value).not_().matches_pattern(pattern)


def test_not_starts_with_reports_the_string_and_the_prefix() -> None:
    value = "abc"
    prefix = "a"

    Assert.that(value).not_().starts_with("b")
    with pytest.raises(
        AssertionError,
        match=re.escape(f"Expected {value!r} not to start with {prefix!r}"),
    ):
        Assert.that(value).not_().starts_with(prefix)


def test_not_ends_with_reports_the_string_and_the_suffix() -> None:
    value = "abc"
    suffix = "c"

    Assert.that(value).not_().ends_with("b")
    with pytest.raises(
        AssertionError,
        match=re.escape(f"Expected {value!r} not to end with {suffix!r}"),
    ):
        Assert.that(value).not_().ends_with(suffix)


def test_is_err_returns_the_narrowed_error() -> None:
    error = ValueError("a")
    result: Result[int, Exception] = Err(error)

    narrowed: ValueError = Assert.that(result).is_err(ValueError)

    Assert.that(narrowed).matches(error)


def test_is_err_reports_an_ok_result() -> None:
    value = 1

    with pytest.raises(
        AssertionError,
        match=re.escape(f"Expected an Err of ValueError, but got Ok: {value}"),
    ):
        _ = Assert.that(Ok(value)).is_err(ValueError)


def test_is_err_reports_the_expected_and_actual_error_types() -> None:
    error = KeyError("a")

    with pytest.raises(
        AssertionError,
        match=re.escape(f"Expected an Err of ValueError, but got Err of KeyError: {error}"),
    ):
        _ = Assert.that(Err(error)).is_err(ValueError)


def test_is_ok_returns_the_value() -> None:
    value = 1
    result: Result[int, Exception] = Ok(value)

    Assert.that(Assert.that(result).is_ok()).matches(value)


def test_is_ok_reports_the_error() -> None:
    error = ValueError("a")

    with pytest.raises(
        AssertionError,
        match=re.escape(f"Expected Ok, but got Err of ValueError: {error}"),
    ):
        _ = Assert.that(Err(error)).is_ok()


class TestTypeChecks:
    @staticmethod
    def _pyrefly_error_kinds(source: str) -> list[str]:
        app_dir = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as snippet_dir:
            snippet = Path(snippet_dir) / "snippet.py"
            _ = snippet.write_text("from assertions import Assert\n\n" + source)
            result = subprocess.run(
                [
                    Path(sys.executable).parent / "pyrefly",
                    "check",
                    snippet,
                    "--config",
                    app_dir / "pyrefly.toml",
                    "--output-format",
                    "min-text",
                ],
                cwd=app_dir,
                capture_output=True,
                text=True,
                check=False,
            )
        output = result.stdout + result.stderr
        # Without the summary line, pyrefly crashed rather than checked the snippet.
        if not re.search(r"INFO \d+ errors?$", output, re.MULTILINE):
            pytest.fail(f"pyrefly did not check the snippet:\n{output}")
        return [line.rsplit(" ", 1)[-1] for line in output.splitlines() if line.startswith("ERROR")]

    @pytest.mark.parametrize(
        ("source", "error_kind"),
        [
            ('Assert.that(1).matches("a")', "[bad-argument-type]"),
            ('Assert.that(1).in_container(["a"])', "[bad-argument-type]"),
            ('Assert.that(1).not_in_container(["a"])', "[bad-argument-type]"),
            ('Assert.that(1).matches_populated_exactly("a")', "[bad-argument-type]"),
            ('Assert.that(1).matches_populated_containing("a")', "[bad-argument-type]"),
            ('Assert.that([1]).container_exactly(["a"])', "[bad-argument-type]"),
            ('Assert.that([1]).all_in(["a"])', "[bad-argument-type]"),
            ('Assert.that([1]).none_in(["a"])', "[bad-argument-type]"),
            ("Assert.that(1).all_in([1])", "[missing-attribute]"),
            ('Assert.that("abc").all_in(["a"])', "[missing-attribute]"),
            ("Assert.that(1).has_length(1)", "[bad-argument-type]"),
            ("Assert.that(1).is_true()", "[bad-argument-type]"),
            ('Assert.that(1).contains("a")', "[bad-argument-type]"),
            ('Assert.that(1).matches_pattern("a")', "[bad-argument-type]"),
            ('Assert.that(1).starts_with("a")', "[bad-argument-type]"),
            ('Assert.that(1).ends_with("a")', "[bad-argument-type]"),
            ('Assert.that(1).not_().matches("a")', "[bad-argument-type]"),
            ('Assert.that(1).not_().contains("a")', "[bad-argument-type]"),
            ('Assert.that(1).not_().matches_pattern("a")', "[bad-argument-type]"),
            ('Assert.that(1).not_().starts_with("a")', "[bad-argument-type]"),
            ('Assert.that(1).not_().ends_with("a")', "[bad-argument-type]"),
            ("Assert.that(1).is_err(ValueError)", "[bad-argument-type]"),
            ("Assert.that(1).is_ok()", "[bad-argument-type]"),
            (
                "narrowed: str = Assert.that(1 if 1 > 0 else None).exists()",
                "[bad-assignment]",
            ),
        ],
    )
    def test_pyrefly_rejects_a_mismatched_expected_value(
        self,
        source: str,
        error_kind: str,
    ) -> None:
        Assert.that(error_kind).in_container(self._pyrefly_error_kinds(source))

    @pytest.mark.parametrize(
        "source",
        [
            "Assert.that([1]).all_in({1, 2})",
            "Assert.that((1,)).container_exactly([1])",
            "Assert.that(range(1)).none_in([1])",
            "Assert.that(frozenset({1})).all_in([1])",
        ],
    )
    def test_pyrefly_accepts_a_matching_expected_value(self, source: str) -> None:
        Assert.that(self._pyrefly_error_kinds(source)).matches([])
