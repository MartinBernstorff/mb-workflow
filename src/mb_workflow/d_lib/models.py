from pydantic import BaseModel, ConfigDict, RootModel
from pydantic.alias_generators import to_camel


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Value[T](RootModel[T]):
    model_config = ConfigDict(frozen=True)


class Payload(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        frozen=True,
        validate_by_name=True,
        validate_by_alias=True,
        alias_generator=to_camel,
    )
