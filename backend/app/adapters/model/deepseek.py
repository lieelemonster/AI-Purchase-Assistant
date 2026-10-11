import json
from typing import Any, Dict, Optional

import openai
from openai import AsyncOpenAI

from app.adapters.model.base import ModelGateway, ModelGatewayError

DEFAULT_MODEL = "deepseek-flash"
BASE_URL = "https://api.deepseek.com"


def classify_model_error(exc: Exception) -> ModelGatewayError:
    if isinstance(exc, (openai.APITimeoutError, TimeoutError)):
        return ModelGatewayError("timeout")
    if isinstance(exc, openai.AuthenticationError):
        return ModelGatewayError("auth")
    if isinstance(exc, openai.RateLimitError):
        return ModelGatewayError("quota")
    if isinstance(exc, openai.APIConnectionError):
        return ModelGatewayError("network")
    if isinstance(exc, openai.APIStatusError):
        if exc.status_code in (401, 403):
            return ModelGatewayError("auth")
        if exc.status_code in (402, 429):
            return ModelGatewayError("quota")
    return ModelGatewayError("unknown")


class DeepSeekGateway(ModelGateway):
    """DeepSeek 官方兼容 OpenAI 的接口。思考模式关闭，避免 JSON 结果被推理文本打断。"""

    def __init__(self, api_key: str, *, model: str = DEFAULT_MODEL, timeout_s: float = 20, client: Optional[AsyncOpenAI] = None):
        self.model_name = model
        self.timeout_s = timeout_s
        self._client = client or AsyncOpenAI(api_key=api_key, base_url=BASE_URL, timeout=timeout_s)

    async def _complete(self, *, task: str, payload: Dict[str, Any], output_schema: Dict[str, Any]) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": task + "\n只返回一个 JSON 对象，不要使用 Markdown。"},
                    {"role": "user", "content": json.dumps(
                        {"payload": payload, "json_schema": output_schema}, ensure_ascii=False)},
                ],
                response_format={"type": "json_object"},
                extra_body={"thinking": {"type": "disabled"}},
                timeout=self.timeout_s,
            )
        except Exception as exc:
            raise classify_model_error(exc) from exc
        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise ModelGatewayError("invalid_output", "模型没有返回内容")
        return content
