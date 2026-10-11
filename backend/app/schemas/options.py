from typing import Annotated, List

from pydantic import BaseModel, ConfigDict, Field, model_validator

StableId = Annotated[str, Field(pattern=r"^[a-z0-9_]+$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OptionItem(StrictModel):
    id: StableId
    label: str = Field(min_length=1)


class Question(StrictModel):
    id: StableId
    label: str = Field(min_length=1)
    multiple: bool
    options: List[OptionItem] = Field(min_length=2)

    @model_validator(mode="after")
    def option_ids_unique(self):
        ids = [o.id for o in self.options]
        if len(ids) != len(set(ids)):
            raise ValueError(f"问题 {self.id} 中存在重复的选项 ID")
        return self


class OptionConfig(StrictModel):
    category_id: str
    version: str = Field(min_length=1)
    questions: List[Question] = Field(min_length=1)

    @model_validator(mode="after")
    def question_ids_unique(self):
        ids = [q.id for q in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError(f"品类 {self.category_id} 中存在重复的问题 ID")
        return self
