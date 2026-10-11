from typing import List

from pydantic import BaseModel


class Category(BaseModel):
    id: str
    name: str


class CategoryList(BaseModel):
    categories: List[Category]
