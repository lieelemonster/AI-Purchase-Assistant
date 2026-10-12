from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

StableId = Annotated[str, Field(pattern=r"^[a-z0-9_]+$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OptionItem(StrictModel):
    id: StableId
    label: str = Field(min_length=1)


class ShowClause(StrictModel):
    """某个已回答的问题命中其中任一选项。"""

    question_id: StableId
    option_ids: List[StableId] = Field(min_length=1)


class ShowWhen(StrictModel):
    """全部 all_of 成立，并且 any_of 为空或至少命中一条时，才显示这道题。"""

    all_of: List[ShowClause] = []
    any_of: List[ShowClause] = []

    @model_validator(mode="after")
    def needs_a_clause(self):
        if not self.all_of and not self.any_of:
            raise ValueError("显示条件至少要有一条")
        return self


class Question(StrictModel):
    id: StableId
    label: str = Field(min_length=1)
    multiple: bool = False
    options: List[OptionItem] = []
    note: Optional[str] = None
    kind: Literal["choice", "text", "number"] = "choice"
    required: bool = False
    show_when: Optional[ShowWhen] = None

    @model_validator(mode="after")
    def option_ids_unique(self):
        if self.kind == "choice" and len(self.options) < 2:
            raise ValueError(f"问题 {self.id} 至少要有两个选项")
        if self.kind != "choice" and self.options:
            raise ValueError(f"问题 {self.id} 不是选择题，不能带选项")
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
