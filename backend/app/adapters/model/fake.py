from typing import Any, Dict, List, Sequence, Union

from app.adapters.model.base import ModelGateway, ModelGatewayError

ScriptedReply = Union[str, ModelGatewayError]


class FakeModelGateway(ModelGateway):
    """按顺序返回预设回复的模拟模型，供测试使用，不产生调用费用。"""

    def __init__(self, replies: Sequence[ScriptedReply]):
        self._replies = list(replies)
        self.calls: List[Dict[str, Any]] = []

    async def _complete(self, *, task: str, payload: Dict[str, Any], output_schema: Dict[str, Any]) -> str:
        self.calls.append({"task": task, "payload": payload, "output_schema": output_schema})
        if not self._replies:
            raise RuntimeError("FakeModelGateway 没有更多预设回复")
        reply = self._replies.pop(0)
        if isinstance(reply, ModelGatewayError):
            raise reply
        return reply
