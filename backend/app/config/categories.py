import json
from functools import lru_cache
from pathlib import Path
from typing import FrozenSet

from app.schemas.category import CategoryList

CATEGORIES_FILE = Path(__file__).parent / "categories.json"


@lru_cache(maxsize=1)
def load_categories() -> CategoryList:
    data = json.loads(CATEGORIES_FILE.read_text(encoding="utf-8"))
    categories = CategoryList.model_validate(data)
    ids = [c.id for c in categories.categories]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{CATEGORIES_FILE.name} 中存在重复的品类 ID")
    return categories


def category_ids() -> FrozenSet[str]:
    return frozenset(c.id for c in load_categories().categories)
