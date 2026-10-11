import json
from abc import ABC, abstractmethod
from typing import Any, Dict, Literal, Type, TypeVar

from pydantic import BaseModel, ValidationError

ModelErrorKind = Literal["timeout", "auth", "quota", "network", "invalid_output", "unknown"]

T = TypeVar("T", bound=BaseModel)


class ModelGatewayError(Exception):
    def __init__(self, kind: ModelErrorKind, message: str = ""):
        super().__init__(f"{kind}: {message}" if message else kind)
        self.kind = kind


class ModelGateway(ABC):
    """推荐核心调用大模型的唯一入口；更换供应商只需实现 _complete。"""

    async def generate_json(self, *, task: str, payload: Dict[str, Any], output_schema: Type[T]) -> T:
        raw = await self._complete(task=task, payload=payload, output_schema=output_schema.model_json_schema())
        return parse_model_output(raw, output_schema)

    @abstractmethod
    async def _complete(self, *, task: str, payload: Dict[str, Any], output_schema: Dict[str, Any]) -> str:
        """返回模型的原始文本输出；失败时抛出 ModelGatewayError。"""


def parse_model_output(raw: str, output_schema: Type[T]) -> T:
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as e:
        raise ModelGatewayError("invalid_output", f"模型输出不是合法 JSON：{e}") from e
    try:
        return output_schema.model_validate(data)
    except ValidationError as e:
        raise ModelGatewayError("invalid_output", f"模型输出不符合预期结构：{e}") from e
