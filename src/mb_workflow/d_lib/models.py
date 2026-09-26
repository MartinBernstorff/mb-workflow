from typing import Self

from pydantic import BaseModel, ConfigDict, RootModel
from pydantic.alias_generators import to_camel


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Value[T](RootModel[T]):
    model_config = ConfigDict(frozen=True)

    @classmethod
    def from_nullable(cls, value: T | None) -> Self | None:
        return None if value is None else cls(value)


class Payload(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        frozen=True,
        validate_by_name=True,
        validate_by_alias=True,
        alias_generator=to_camel,
    )
