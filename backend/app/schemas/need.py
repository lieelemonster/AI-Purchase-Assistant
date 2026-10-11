from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config.categories import category_ids

NonEmptyStr = Annotated[str, Field(min_length=1)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OptionAnswer(StrictModel):
    question_id: NonEmptyStr
    option_ids: List[NonEmptyStr]


class OptionSource(StrictModel):
    kind: Literal["option"]
    question_id: NonEmptyStr
    option_id: NonEmptyStr


class FreeTextSource(StrictModel):
    kind: Literal["free_text"]
    quote: NonEmptyStr


RequirementSource = Annotated[Union[OptionSource, FreeTextSource], Field(discriminator="kind")]


class Requirement(StrictModel):
    requirement_id: NonEmptyStr
    topic: NonEmptyStr
    statement: NonEmptyStr
    strictness: Literal["hard", "soft", "unknown"] = "unknown"
    source: RequirementSource


class Conflict(StrictModel):
    description: NonEmptyStr
    requirement_ids: List[NonEmptyStr]


class MarketContext(StrictModel):
    region: Optional[str] = None
    currency: Optional[str] = None


class NeedProfile(StrictModel):
    category_id: str
    option_answers: List[OptionAnswer] = []
    free_text: str = ""
    requirements: List[Requirement] = []
    unknowns: List[NonEmptyStr] = []
    conflicts: List[Conflict] = []
    market_context: MarketContext = MarketContext()

    @field_validator("category_id")
    @classmethod
    def category_must_exist(cls, value: str) -> str:
        if value not in category_ids():
            raise ValueError(f"未知品类：{value}")
        return value
