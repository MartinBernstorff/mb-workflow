from typing import Self

from pydantic import RootModel


class PersonName(RootModel[str]):
    @staticmethod
    def fake() -> PersonName:
        return PersonName("Ada")


class Greeting(RootModel[str]):
    @staticmethod
    def fake() -> Greeting:
        return Greeting(f"Hello, {PersonName.fake().root}!")

    @classmethod
    def to(cls, name: PersonName) -> Self:
        return cls(f"Hello, {name.root}!")
