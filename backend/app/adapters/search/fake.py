from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from app.adapters.search.base import SearchGateway, SearchGatewayError, SearchHit

ScriptedResult = Union[Sequence[SearchHit], SearchGatewayError]


class FakeSearchGateway(SearchGateway):
    """按查询词返回预设结果的模拟搜索，供测试使用。未预设的查询返回空列表。"""

    def __init__(self, responses: Optional[Mapping[str, ScriptedResult]] = None):
        self._responses = dict(responses or {})
        self.calls: List[Dict[str, Any]] = []

    async def search(
        self,
        query: str,
        *,
        region: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 10,
    ) -> List[SearchHit]:
        self.calls.append({"query": query, "region": region, "language": language, "limit": limit})
        result = self._responses.get(query, [])
        if isinstance(result, SearchGatewayError):
            raise result
        return list(result)[:limit]
