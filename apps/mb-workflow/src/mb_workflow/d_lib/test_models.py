from mb_workflow.d_lib.models import Value


class Word(Value[str]): ...


def test_a_value_wraps_what_it_is_given() -> None:
    assert Word.from_nullable("mud") == Word("mud")


def test_nothing_wraps_to_none() -> None:
    assert Word.from_nullable(None) is None
