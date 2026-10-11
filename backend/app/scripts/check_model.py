"""检查 DeepSeek 是否可用：python -m app.scripts.check_model"""

import asyncio
import os
import sys

from pydantic import BaseModel

from app.adapters.model.base import ModelGatewayError
from app.adapters.model.deepseek import DeepSeekGateway
from app.config.settings import load_project_env, load_runtime_config, load_secrets


class Ping(BaseModel):
    ok: bool


async def main() -> int:
    load_project_env()
    secrets = load_secrets()
    if secrets.model_api_key is None:
        print("unavailable: auth")
        return 1
    timeout_s = float(os.environ.get("DEEPSEEK_TIMEOUT_S") or load_runtime_config().call_timeout_s)
    gateway = DeepSeekGateway(secrets.model_api_key.get_secret_value(), timeout_s=timeout_s)
    try:
        result = await gateway.generate_json(
            task="这是连通性检查。返回 {\"ok\": true}。",
            payload={},
            output_schema=Ping,
        )
    except ModelGatewayError as exc:
        print(f"unavailable: {exc.kind}")
        return 1
    if not result.ok:
        print("unavailable: invalid_output")
        return 1
    print(f"ok {gateway.model_name}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
