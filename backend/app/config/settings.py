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
    rate_limit_per_minute: PositiveInt
    max_concurrent_requests: PositiveInt


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


ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def load_project_env(path: Path = ENV_FILE) -> None:
    """读取 backend/.env。已经存在的环境变量优先，方便临时换密钥或超时做检查。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def load_secrets(env: Mapping[str, str] = os.environ) -> Secrets:
    return Secrets(
        model_api_key=env.get("MODEL_API_KEY") or None,
        search_api_key=env.get("SEARCH_API_KEY") or None,
    )
