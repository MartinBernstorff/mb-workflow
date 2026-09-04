from mb_workflow.greeting import Greeting, PersonName


def test_greeting_addresses_the_person() -> None:
    assert Greeting.to(PersonName.fake()) == Greeting.fake()
