import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pydantic
import pytest

from assertions import Assert


class Pet(pydantic.BaseModel):
    name: str
    tags: list[str]


class Owner(pydantic.BaseModel):
    pet: Pet


def test_matches_passes_on_equal_values() -> None:
    Assert.that(1).matches(1)


def test_matches_reports_both_values() -> None:
    with pytest.raises(AssertionError, match="1 != 2"):
        Assert.that(1).matches(2)


def test_matches_compares_sequences_by_their_elements() -> None:
    Assert.that([1, 2]).matches((1, 2))


def test_matches_reports_differing_sequences() -> None:
    with pytest.raises(AssertionError, match=r"\[1, 2\] != \(2, 1\)"):
        Assert.that([1, 2]).matches((2, 1))


def test_matches_compares_models_by_value() -> None:
    Assert.that(Pet(name="a", tags=[])).matches(Pet(name="a", tags=[]))


def test_matches_reports_both_model_dumps() -> None:
    with pytest.raises(AssertionError, match=r"'name': 'a'.*'name': 'b'"):
        Assert.that(Pet(name="a", tags=[])).matches(Pet(name="b", tags=[]))


def test_matches_populated_exactly_ignores_unset_fields() -> None:
    Assert.that(Pet(name="a", tags=["x"])).matches_populated_exactly(
        Pet.model_construct(name="a"),
    )


def test_matches_populated_exactly_reports_the_differing_path() -> None:
    with pytest.raises(AssertionError, match=r"tags: 1 element != 2 elements"):
        Assert.that(Pet(name="a", tags=["x"])).matches_populated_exactly(
            Pet.model_construct(tags=["x", "y"]),
        )


def test_matches_populated_exactly_reports_the_nested_element_path() -> None:
    with pytest.raises(AssertionError, match=r"pet\.tags\[0\]: x != y"):
        Assert.that(Owner(pet=Pet(name="a", tags=["x"]))).matches_populated_exactly(
            Owner.model_construct(pet=Pet.model_construct(tags=["y"])),
        )


def test_matches_populated_exactly_reports_differing_types_by_name() -> None:
    actual: pydantic.BaseModel = Pet(name="a", tags=[])

    with pytest.raises(AssertionError, match=r"Pet != Owner"):
        Assert.that(actual).matches_populated_exactly(Owner.model_construct())


def test_matches_populated_containing_allows_extra_list_elements() -> None:
    Assert.that(Pet(name="a", tags=["x", "y"])).matches_populated_containing(
        Pet.model_construct(tags=["y"]),
    )


def test_matches_populated_containing_reports_the_missing_element() -> None:
    with pytest.raises(AssertionError, match=r"tags: <missing> != z"):
        Assert.that(Pet(name="a", tags=["x"])).matches_populated_containing(
            Pet.model_construct(tags=["z"]),
        )


def test_in_container_passes_when_present() -> None:
    Assert.that(1).in_container([1, 2])


def test_in_container_reports_item_and_container() -> None:
    with pytest.raises(AssertionError, match=r"3 not found in container \[1, 2\]"):
        Assert.that(3).in_container([1, 2])


def test_not_in_container_passes_when_absent() -> None:
    Assert.that(3).not_in_container([1, 2])


def test_not_in_container_reports_item_and_container() -> None:
    with pytest.raises(AssertionError, match=r"1 unexpectedly found in container \[1, 2\]"):
        Assert.that(1).not_in_container([1, 2])


def test_container_exactly_ignores_order() -> None:
    Assert.that([1, 2]).container_exactly({2, 1})


def test_container_exactly_reports_missing_and_extra_items() -> None:
    with pytest.raises(AssertionError, match=r"Missing: \[3\]\n\tExtra: \[1\]"):
        Assert.that([1, 2]).container_exactly([2, 3])


def test_all_in_passes_on_a_subset() -> None:
    Assert.that((1, 2)).all_in([1, 2, 3])


def test_all_in_accepts_any_sequence() -> None:
    Assert.that(range(1, 3)).all_in([1, 2, 3])


def test_all_in_reports_the_missing_items() -> None:
    with pytest.raises(AssertionError, match=r"Items not found in container: \[4\]"):
        Assert.that([1, 4]).all_in([1, 2, 3])


def test_none_in_passes_on_disjoint_items() -> None:
    Assert.that(frozenset({4})).none_in([1, 2, 3])


def test_none_in_reports_the_present_items() -> None:
    with pytest.raises(AssertionError, match=r"Unexpected items found in container: \[1\]"):
        Assert.that([1, 4]).none_in([1, 2, 3])


def test_all_passes_when_every_item_satisfies_the_predicate() -> None:
    Assert.that([2, 4]).all(lambda n: n % 2 == 0, lambda n: f"{n} is odd")


def test_all_reports_each_failing_item() -> None:
    with pytest.raises(AssertionError, match=r"\['1 is odd', '3 is odd'\]"):
        Assert.that([1, 2, 3]).all(lambda n: n % 2 == 0, lambda n: f"{n} is odd")


def test_has_length_passes_on_the_length() -> None:
    Assert.that("abc").has_length(3)


def test_has_length_reports_the_length() -> None:
    with pytest.raises(AssertionError, match=r"length 2, but it had length 1: \[1\]"):
        Assert.that([1]).has_length(2)


def test_is_true_passes_on_true() -> None:
    Assert.that(True).is_true()


def test_is_true_rejects_false() -> None:
    with pytest.raises(AssertionError, match="Expected True, but it was False"):
        Assert.that(False).is_true()


def test_is_false_passes_on_false() -> None:
    Assert.that(False).is_false()


def test_is_false_rejects_true() -> None:
    with pytest.raises(AssertionError, match="Expected False, but it was True"):
        Assert.that(True).is_false()


def test_is_instance_returns_the_narrowed_value() -> None:
    value: int | str = "a"

    narrowed: str = Assert.that(value).is_instance(str)

    Assert.that(narrowed).matches("a")


def test_is_instance_reports_the_expected_and_actual_types() -> None:
    value: int | str = 1

    with pytest.raises(AssertionError, match="Expected an instance of str, but got int: 1"):
        _ = Assert.that(value).is_instance(str)


def test_exists_returns_the_narrowed_value() -> None:
    value: int | None = 1

    narrowed: int = Assert.that(value).exists()

    Assert.that(narrowed).matches(1)


def test_exists_rejects_none() -> None:
    value: int | None = None

    with pytest.raises(AssertionError, match="Expected value to exist, but it was None"):
        _ = Assert.that(value).exists()


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
