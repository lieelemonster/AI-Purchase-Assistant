import json
from functools import lru_cache
from pathlib import Path

from app.config.categories import category_ids
from app.schemas.options import OptionConfig

OPTIONS_DIR = Path(__file__).parent / "options"


class UnknownCategoryError(LookupError):
    pass


@lru_cache(maxsize=None)
def load_options(category_id: str) -> OptionConfig:
    if category_id not in category_ids():
        raise UnknownCategoryError(category_id)
    path = OPTIONS_DIR / f"{category_id}.json"
    config = OptionConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))
    if config.category_id != category_id:
        raise ValueError(f"{path.name} 中的 category_id 应为 {category_id}")
    return config
