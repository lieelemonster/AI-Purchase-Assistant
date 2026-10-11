import json
import os
from pathlib import Path
from typing import Mapping, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    SecretStr,
    ValidationError,
)

RUNTIME_FILE = Path(__file__).parent / "runtime.json"


class ConfigError(Exception):
    pass


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_candidates: PositiveInt
    max_search_calls: PositiveInt
    max_pages: PositiveInt
    max_page_bytes: PositiveInt
    call_timeout_s: PositiveFloat
    request_timeout_s: PositiveFloat
    max_retries: NonNegativeInt
    concurrency: PositiveInt
    source_min_interval_s: NonNegativeFloat
    model_max_output_tokens: PositiveInt


class Secrets(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_api_key: Optional[SecretStr] = None
    search_api_key: Optional[SecretStr] = None


def load_runtime_config(path: Path = RUNTIME_FILE) -> RuntimeConfig:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return RuntimeConfig.model_validate(data)
    except (OSError, json.JSONDecodeError, ValidationError) as e:
        raise ConfigError(f"{path.name} 配置有误：\n{e}") from e


def load_secrets(env: Mapping[str, str] = os.environ) -> Secrets:
    return Secrets(
        model_api_key=env.get("MODEL_API_KEY") or None,
        search_api_key=env.get("SEARCH_API_KEY") or None,
    )
