import json
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config.categories import category_ids

FIELDS_DIR = Path(__file__).parent / "fields"


class FieldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1)
    pconline_labels: List[str] = Field(min_length=1)


class FieldTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: str
    version: str = Field(min_length=1)
    fields: List[FieldSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def ids_and_labels_unique(self):
        ids = [f.id for f in self.fields]
        labels = [label for f in self.fields for label in f.pconline_labels]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{self.category_id} 字段表中存在重复的字段 ID")
        if len(labels) != len(set(labels)):
            raise ValueError(f"{self.category_id} 字段表中同一个太平洋字段名对应了多个字段")
        return self


@lru_cache(maxsize=None)
def load_field_table(category_id: str) -> FieldTable:
    if category_id not in category_ids():
        raise LookupError(category_id)
    path = FIELDS_DIR / f"{category_id}.json"
    table = FieldTable.model_validate(json.loads(path.read_text(encoding="utf-8")))
    if table.category_id != category_id:
        raise ValueError(f"{path.name} 中的 category_id 应为 {category_id}")
    return table
